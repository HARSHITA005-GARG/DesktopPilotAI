from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_ollama import ChatOllama
from core.state import AssistantState

# Import the new native tools
from tools.system_tools import manage_local_file, log_interaction

# 1. Initialize the LLM and bind the tools natively
llm = ChatOllama(model="llama3.1", temperature=0.1)
tools = [manage_local_file]
llm_with_tools = llm.bind_tools(tools)

# 2. Define the Agent Node
def agent_node(state: AssistantState):
    """The Brain: Evaluates the conversation and decides whether to chat or use a tool."""
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}

# 3. Define the Logging Gateway Node
def logging_node(state: AssistantState):
    """The Gateway: Saves the interaction to the hard drive before closing the loop."""
    messages = state["messages"]
    
    # Safely extract the last human message and the AI's text response
    user_msg = next((m.content for m in reversed(messages) if m.type == "human"), "")
    ai_msg = next((m.content for m in reversed(messages) if m.type == "ai" and m.content), "")
    
    if user_msg and ai_msg:
        log_interaction(user_msg, ai_msg)
        
    return state

# 4. Build the Graph Architecture
builder = StateGraph(AssistantState)

# Add the three core nodes
builder.add_node("agent", agent_node)
builder.add_node("tools", ToolNode(tools)) # LangGraph's native tool executor
builder.add_node("logger", logging_node)

# Step 1: Always start at the Agent
builder.add_edge(START, "agent")

# Step 2: The conditional router
# If the AI called a tool, go to 'tools'. If it just chatted, go to 'logger'.
builder.add_conditional_edges(
    "agent",
    tools_condition,
    {
        "tools": "tools",
        END: "logger" 
    }
)

# Step 3: Tools must always return their output back to the Agent to read
builder.add_edge("tools", "agent")

# Step 4: After logging is done, the cycle safely ends
builder.add_edge("logger", END)

# Compile the multi-agent graph
orchestrator_app = builder.compile()