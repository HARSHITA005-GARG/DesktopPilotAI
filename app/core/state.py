from typing import Annotated, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AssistantState(TypedDict):
    """
    Global state for the Local Agentic Voice Assistant.
    Flows continuously through the LangGraph nodes.
    """
    
    # --- Conversational History ---
    # add_messages handles appending new turns without overwriting
    messages: Annotated[list[BaseMessage], add_messages]
    
    # --- Context & Memory ---
    # Injected context from ChromaDB based on the current utterance
    retrieved_context: str
    
    # --- Execution Sandbox ---
    # Captures tool usage and Docker execution results
    code_to_execute: str
    sandbox_stdout: str
    sandbox_stderr: str
    
    # --- Orchestration Flags ---
    # True if the code ran successfully, False if an error needs LLM correction
    execution_complete: bool