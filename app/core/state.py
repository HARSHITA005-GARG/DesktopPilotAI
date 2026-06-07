from typing import Annotated, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AssistantState(TypedDict):
    """Simplified Global State for Phase 2 Native Tool Calling."""
    messages: Annotated[list[BaseMessage], add_messages]