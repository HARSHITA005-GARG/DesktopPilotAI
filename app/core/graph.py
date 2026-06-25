import os

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from core.state import AssistantState
from tools.system_tools import (
    navigate_and_read,
    update_workspace_file,
    read_local_file,
    search_web,
    perform_calculation,
    open_application
)
from memory.worker import MemoryWorker
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_groq import ChatGroq
memory_worker = MemoryWorker()

# ==========================================
# 1. THE SPLIT BRAIN MODELS
# ==========================================

# Brain A: The Orchestrator (Fast, Conversational, No Tools)
orchestrator_llm = ChatOllama(
    model="llama3.2:3b", 
    temperature=0.3, 
    streaming=True
)
# 1. Define your 100% Offline Local Model
local_coder = ChatOllama(
    model="qwen2.5-coder:3b", # The lightweight local version
    temperature=0.2
)
# Brain B: The Codex Core (Heavy Reasoning, Large Context, Has Tools)
# NOTE: If you have a local coding model, use it here (e.g., "qwen2.5-coder:7b"). 
# Alternatively, you can plug ChatAnthropic or ChatOpenAI in here for true Codex-level ability.
coding_agent = ChatGroq(
    model="qwen/qwen3-32b", # Or "llama-3.1-70b-versatile"
    temperature=0.2,            # Low temp for accurate code
    api_key=os.environ.get("GROQ_API_KEY"),
    max_retries=1,
    timeout=60,                # Longer timeout for coding tasks
).with_fallbacks([local_coder])  # Fallback to local if Groq fails

# Bind tools ONLY to the Codex Core
tools = [update_workspace_file, open_application, read_local_file, search_web, perform_calculation, navigate_and_read]
coder_with_tools = coding_agent.bind_tools(tools)
local_coder_with_tools = local_coder.bind_tools(tools)  # Ensure local fallback also has tools
# ==========================================
# 2. THE GRAPH NODES
# ==========================================

async def conversational_node(state: AssistantState, config: RunnableConfig):
    """Handles basic chat, greetings, and questions instantly."""
    sys_prompt = SystemMessage(
        content=(
            "You are a helpful programming assistant. Answer the user's questions clearly and conversationally. "
            "Do not write complex scripts here, just chat naturally."
        )
    )
    messages = [sys_prompt] + state["messages"]
    response = await orchestrator_llm.ainvoke(messages, config)
    return {"messages": [response]}

async def coder_node(state: AssistantState, config: RunnableConfig):
    """The heavy-lifter. Writes files, executes code, and builds applications."""
    user_msg = state["messages"][-1].content
    context = memory_worker.retrieve_context(user_msg)
    
    sys_prompt = SystemMessage(
        content=(
            "You are an elite Autonomous AI Developer. You have direct access to the user's file system.\n"
            "=== STT ERROR CORRECTION ===\n"
            "The user is using a microphone. Fix phonetic typos (e.g. 'hdml' -> HTML) before coding.\n\n"
            "=== CODING DIRECTIVES ===\n"
            "1. You MUST use the `update_workspace_file` tool to save your code. NEVER output raw code blocks in the chat.\n"
            "2. Always output the absolute, complete file content. Never use placeholders.\n\n"
            f"=== WORKSPACE CONTEXT ===\n{context}"
        )
    )
    messages = [sys_prompt] + state["messages"]
    response = await coder_with_tools.ainvoke(messages, config)
    return {"messages": [response]}

# ==========================================
# 3. THE ROUTER (The Traffic Cop)
# ==========================================

async def route_intent(state: AssistantState) -> str:
    """Uses Llama 3.2 to intelligently classify the user's intent."""
    if not state["messages"]:
        return "chat"
        
    user_message = state["messages"][-1].content
    print(f"\n[Router] Asking Llama 3.2 to classify intent for: '{user_message}'")
    
    # We constrain Llama 3.2 to reply with exactly one word so it acts as a perfect switch
    router_prompt = SystemMessage(content=(
        "You are an expert intent classification AI. Read the user's input and reply with EXACTLY ONE WORD from the following two choices:\n\n"
        "1. 'CODER' - If the user is asking you to perform an action: open an application (e.g., 'open excel', 'teams for me'), write code, manipulate files, search the web, or do math.\n"
        "2. 'CHAT' - If the user is just saying hello, making casual small talk, or asking a conversational question.\n\n"
        "CRITICAL: Do not include any punctuation, explanations, or conversational filler. Reply ONLY with the word CODER or CHAT."
    ))
    
    try:
        # We use the existing orchestrator_llm (Llama 3.2) for zero-cost local routing
        response = await orchestrator_llm.ainvoke([router_prompt, HumanMessage(content=user_message)])
        decision = response.content.strip().upper()
        
        # Parse the LLM's response
        if "CODER" in decision:
            print("[Router] Llama 3.2 Decision: ACTION REQUIRED -> Routing to Codex Core...")
            return "coder"
        else:
            print("[Router] Llama 3.2 Decision: CASUAL CHAT -> Routing to Orchestrator...")
            return "chat"
            
    except Exception as e:
        print(f"[Router Error] Llama 3.2 failed to route: {str(e)}. Defaulting to chat.")
        return "chat"

# ==========================================
# 4. BUILD THE GRAPH
# ==========================================

builder = StateGraph(AssistantState)

# Add Nodes
builder.add_node("chat_node", conversational_node)
builder.add_node("coder_node", coder_node)
builder.add_node("tools", ToolNode(tools))

# Route from Start
builder.add_conditional_edges(
    START,
    route_intent,
    {
        "chat": "chat_node",
        "coder": "coder_node"
    }
)

# Chat goes straight to the end
builder.add_edge("chat_node", END)

# Coder can cycle through tools
builder.add_conditional_edges(
    "coder_node",
    tools_condition,
    {
        "tools": "tools",
        END: END,
    }
)
builder.add_edge("tools", "coder_node")

orchestrator_app = builder.compile()