from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from app.agents.schemas import ManualRoomInput, RoomData
from app.config import settings

_flagged_concerns: list = []


@tool
def flag_concern(message: str) -> str:
    """Flag a concern about the manual room input — an implausible dimension,
    a missing obstacle detail, or anything that doesn't add up."""
    _flagged_concerns.append(message)
    return f"Noted: {message}"


def _get_model():
    if settings.llm_provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=0,
        )
    else:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model="claude-sonnet-4-6")


def analyze_manual_room_input(manual_input: ManualRoomInput) -> RoomData:
    """Run the Room Intelligence agent against a manually entered room."""
    _flagged_concerns.clear()

    model = _get_model()
    agent = create_react_agent(
        model,
        tools=[flag_concern],
        state_modifier=(
            "You are the Room Intelligence agent for FurniVision. A user has "
            "manually entered room dimensions instead of uploading photos. "
            "Check the input for anything implausible — e.g. a ceiling height "
            "under 2m, a room narrower than 1m, obstacles that don't make sense "
            "for the stated dimensions — and call flag_concern once per issue "
            "you find. If everything looks reasonable, don't call any tools."
        ),
    )

    agent.invoke({
        "messages": [{
            "role": "user",
            "content": (
                f"Room dimensions: {manual_input.width_m}m x {manual_input.length_m}m, "
                f"ceiling height {manual_input.height_m}m. "
                f"Obstacles: {manual_input.obstacles or 'none listed'}. "
                f"Notes: {manual_input.notes or 'none'}."
            ),
        }]
    })

    return RoomData(
        width_m=manual_input.width_m,
        length_m=manual_input.length_m,
        height_m=manual_input.height_m,
        floor_area_m2=round(manual_input.width_m * manual_input.length_m, 2),
        obstacles=manual_input.obstacles,
        warnings=list(_flagged_concerns),
        photo_path=manual_input.photo_path,
        notes=manual_input.notes,  # NEW
    )
