import os

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from core.state import AssistantState
from tools.system_tools import (
    update_workspace_file,
    read_local_file,
    search_web,
    perform_calculation
)
from memory.worker import MemoryWorker
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

# Brain B: The Codex Core (Heavy Reasoning, Large Context, Has Tools)
# NOTE: If you have a local coding model, use it here (e.g., "qwen2.5-coder:7b"). 
# Alternatively, you can plug ChatAnthropic or ChatOpenAI in here for true Codex-level ability.
coding_agent = ChatGroq(
    model="qwen/qwen3-32b", # Or "llama-3.1-70b-versatile"
    temperature=0.2,            # Low temp for accurate code
    api_key=os.environ.get("GROQ_API_KEY")
)

# Bind tools ONLY to the Codex Core
tools = [update_workspace_file, read_local_file, search_web, perform_calculation]
coder_with_tools = coding_agent.bind_tools(tools)

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

def route_intent(state: AssistantState) -> str:
    """Instantly decides which brain gets the prompt based on action keywords."""
    user_message = state["messages"][-1].content.lower() if state["messages"] else ""
    
    # If the user says any of these words, wake up the Codex Core
    coding_keywords = ["file", "code", "write", "build", "script", "app", "ui", "html", "python", "bug", "fix"]
    
    if any(kw in user_message for kw in coding_keywords):
        print("[Router] Wake word detected. Routing to Codex Core...")
        return "coder"
    
    print("[Router] Casual intent detected. Routing to Orchestrator...")
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