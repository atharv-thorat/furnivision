from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from app.agents.room_intelligence import _get_model
from app.agents.schemas import RoomData, DesignConcepts

_last_design: dict = {}


@tool
def propose_palette(style: str, mood: str) -> dict:
    """Propose a color palette and material set for a given style and mood."""
    result = {"style": style, "mood": mood, "note": "placeholder — real logic later"}
    _last_design["palette"] = result
    return result


@tool
def check_style_room_fit(style: str, floor_area_m2: float, natural_light: str) -> str:
    """Sanity-check whether a proposed style suits the room's size and light conditions."""
    return f"Checked {style} against {floor_area_m2}m2 room with {natural_light} light."


def propose_design(room_data: RoomData, user_style_pref: str) -> DesignConcepts:
    """Run the Design & Material agent given Room Intelligence's output."""
    _last_design.clear()

    model = _get_model()
    agent = create_react_agent(
        model,
        tools=[propose_palette, check_style_room_fit],
        state_modifier=(
            "You are the Design & Material agent for FurniVision. Given room "
            "data and the user's style preference, propose a palette and "
            "materials that suit the room's size and obstacles. Use your tools "
            "rather than guessing."
        ),
    )

    agent.invoke({
        "messages": [{
            "role": "user",
            "content": (
                f"Room: {room_data.floor_area_m2}m2, obstacles: {room_data.obstacles}. "
                f"Room type/notes: {room_data.notes or 'not specified'}. "
                f"User wants style: {user_style_pref}."
            ),
        }]
    })

    return DesignConcepts(
        style=user_style_pref,
        palette=_last_design.get("palette", {}),
    )