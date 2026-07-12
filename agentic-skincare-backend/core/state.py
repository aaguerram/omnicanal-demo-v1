from typing import TypedDict, Annotated, List, Optional, Dict, Any
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    image_url: Optional[str]
    patient_info: Dict[str, Any]  # e.g., {"acne_level": "alto", "skin_type": "grasa", "irritation": "no", "allergies": "ninguna"}
    next_step: str # To help router determine the next node
