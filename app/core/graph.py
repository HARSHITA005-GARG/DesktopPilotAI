import re
from typing import Literal
from langgraph.graph import StateGraph, END
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

# Import our custom modules
from core.state import AssistantState
from memory.worker import MemoryWorker
from sandbox.docker_exec import DockerSandbox

# --- Global Initialization ---
# Instantiate our heavy modules once so they persist across graph executions
memory_worker = MemoryWorker()
sandbox = DockerSandbox()

# Connect to the local 8B model via Ollama
llm = ChatOllama(model="interstellarninja/hermes-2-pro-llama-3-8b", temperature=0.1)

# --- Helper Functions ---
def extract_python_code(text: str) -> str:
    """Extracts raw python code from a markdown block."""
    match = re.search(r"```python\n(.*?)\n```", text, re.DOTALL)
    return match.group(1).strip() if match else ""

# --- Node Definitions ---

def retrieve_memory_node(state: AssistantState) -> dict:
    """
    The Hippocampus: Retrieves relevant vectors based on the latest user message.
    """
    latest_message = state["messages"][-1].content
    context = memory_worker.retrieve_context(latest_message)
    
    # Return partial state update
    return {"retrieved_context": context}

def llm_generation_node(state: AssistantState) -> dict:
    """
    The Prefrontal Cortex: Constructs the prompt, queries the LLM, and parses the output.
    """
    # 1. Construct the System Prompt
    system_prompt = (
        "You are a local, real-time coding assistant. Keep your spoken responses concise. "
        "If asked to write code, output it inside ```python``` markdown blocks.\n\n"
        f"{state.get('retrieved_context', '')}"
    )
    
    # 2. Check if this is a self-correction loop
    if not state.get("execution_complete", True) and state.get("sandbox_stderr"):
        error_msg = f"Your previous code failed with this error:\n{state['sandbox_stderr']}\nPlease fix it."
        messages = state["messages"] + [HumanMessage(content=error_msg)]
    else:
        messages = state["messages"]
        
    full_prompt = [SystemMessage(content=system_prompt)] + messages

    # 3. Invoke the LLM
    # Note: In a true real-time setup, you would use .stream() here and route chunks to Piper TTS.
    # For the graph definition, we wait for the full response to evaluate logic.
    response = llm.invoke(full_prompt)
    response_text = response.content

    # 4. Parse the output to see if it requires sandbox execution
    code_block = extract_python_code(response_text)
    
    if code_block:
        return {
            "messages": [AIMessage(content=response_text)],
            "code_to_execute": code_block,
            "execution_complete": False,  # Flag that we need to route to the sandbox
            "sandbox_stderr": ""          # Clear previous errors
        }
    else:
        # Standard conversational response
        return {
            "messages": [AIMessage(content=response_text)],
            "code_to_execute": "",
            "execution_complete": True
        }

def sandbox_execution_node(state: AssistantState) -> dict:
    """
    The Hands: Executes the generated code in the transient Docker container.
    """
    code = state["code_to_execute"]
    stdout, stderr = sandbox.execute_code(code)
    
    if stderr:
        # Execution failed. Update state to trigger the retry loop.
        return {
            "sandbox_stderr": stderr,
            "sandbox_stdout": "",
            "execution_complete": False
        }
    else:
        # Execution succeeded.
        return {
            "sandbox_stdout": stdout,
            "sandbox_stderr": "",
            "execution_complete": True
        }

# --- Conditional Edge Logic ---

def route_after_llm(state: AssistantState) -> Literal["sandbox_execution_node", "__end__"]:
    """Determines where to go after the LLM speaks."""
    if state.get("code_to_execute") and not state.get("execution_complete"):
        return "sandbox_execution_node"
    return "__end__"

def route_after_sandbox(state: AssistantState) -> Literal["llm_generation_node", "__end__"]:
    """Determines where to go after the Sandbox runs."""
    if state.get("sandbox_stderr"):
        # If there's an error, route back to the LLM to fix it
        return "llm_generation_node"
    return "__end__"

# --- Build and Compile the Graph ---

builder = StateGraph(AssistantState)

# Add Nodes
builder.add_node("retrieve_memory_node", retrieve_memory_node)
builder.add_node("llm_generation_node", llm_generation_node)
builder.add_node("sandbox_execution_node", sandbox_execution_node)

# Add Edges
builder.set_entry_point("retrieve_memory_node")
builder.add_edge("retrieve_memory_node", "llm_generation_node")

# Add Conditional Edges
builder.add_conditional_edges("llm_generation_node", route_after_llm)
builder.add_conditional_edges("sandbox_execution_node", route_after_sandbox)

# Compile into a runnable application
orchestrator_app = builder.compile()