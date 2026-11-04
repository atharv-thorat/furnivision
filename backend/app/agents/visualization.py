import requests
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from app.agents.room_intelligence import _get_model
from app.agents.schemas import RoomData, FurniturePlan, VisualizationOutput
from app.config import settings

_tool_log: dict = {"render_calls": []}
_current_photo_path: dict = {"path": None}

STYLE_PROMPT_HINTS = {
    "scandinavian": "light oak and pale birch wood, soft white and dove-grey fabric, natural linen, minimal clean lines, airy and bright, morning daylight",
    "modern": "matte black and charcoal grey surfaces, brushed steel accents, deep navy and slate fabric, sharp geometric lines, dramatic side lighting",
    "industrial": "dark walnut and raw wood, black leather, exposed matte metal fixtures, weathered concrete textures, warm amber lighting",
    "traditional": "rich mahogany wood, deep burgundy and forest green fabric, ornate brass accents, classic carved details, warm golden lighting",
}


@tool
def render_scene(description: str) -> str:
    """Render a photorealistic scene from a description of the room and furniture layout. Returns a URL to the render."""
    photo_path = _current_photo_path.get("path")
    try:
        if photo_path:
            with open(photo_path, "rb") as f:
                response = requests.post(
                    f"{settings.render_server_url}/render_from_photo",
                    files={"photo": f},
                    data={"description": description, "full_redesign": "false"},
                    timeout=180,
                )
        else:
            response = requests.post(
                f"{settings.render_server_url}/render",
                json={"description": description},
                timeout=120,
            )
        response.raise_for_status()
        data = response.json()
        render_url = f"{settings.render_server_url}{data['path']}"
    except Exception as e:
        render_url = f"ERROR: render request failed - {e}"

    _tool_log["render_calls"].append({"description": description, "url": render_url, "used_photo": bool(photo_path)})
    return render_url


def visualize_design(room_data: RoomData, plan: FurniturePlan, image_description: str = None, design_concepts=None) -> VisualizationOutput:
    _tool_log["render_calls"].clear()
    _current_photo_path["path"] = room_data.photo_path

    model = _get_model()
    agent = create_react_agent(
        model,
        tools=[render_scene],
        state_modifier=(
            "You are the Visualization agent for FurniVision. You have exactly "
            "one job: call the render_scene tool exactly once, passing the "
            "EXACT scene description given to you in the user message, "
            "completely unchanged — do not shorten it, rephrase it, remove "
            "any words, or add your own. Copy it verbatim as the 'description' "
            "argument. Do not respond with plain text — only a tool call "
            "counts as a complete response."
        ),
    )

    item_list = ", ".join(f"a {i['name']}" for i in plan.items)
    style = (design_concepts.style if design_concepts else "").lower()
    style_hint = STYLE_PROMPT_HINTS.get(style, "warm neutral tones, balanced natural lighting")

    # Built deterministically in Python — the style words are guaranteed to
    # be present, not left to the small model to preserve or paraphrase.
    # Furniture first, style modifier second — CLIP truncates at 77 tokens,
    # so whatever matters most has to come first or it gets silently cut.
    short_style = style_hint.split(",")[0].strip() if style_hint else ""
    if image_description and not room_data.photo_path:
        final_description = f"{item_list}, {style} style, {short_style}, {image_description}"
    else:
        final_description = f"{item_list}, {style} style, {short_style}, {room_data.notes or 'bedroom'}"

    message_content = (
        f"Call render_scene now with this exact description as the argument: "
        f'"{final_description}"'
    )

    result = None
    for attempt in range(2):
        try:
            result = agent.invoke(
                {"messages": [{"role": "user", "content": message_content}]},
                config={"recursion_limit": 12},
            )
        except Exception as e:
            if "recursion limit" in str(e).lower():
                print(f"Visualization agent hit the recursion safety limit on attempt {attempt + 1}.")
                result = None
            else:
                raise
        if _tool_log["render_calls"]:
            break
        if attempt == 0:
            print("Visualization agent didn't call the tool on attempt 1 — retrying.")
            message_content += " Remember: call render_scene now with the exact description given."

    # Safety net: if the agent still failed to call the tool after 2 tries,
    # call it directly with the deterministic description rather than
    # returning an empty result.
    if not _tool_log["render_calls"]:
        print("=== Agent never called render_scene — calling it directly as a fallback. ===")
        render_scene.invoke({"description": final_description})

    last_call = _tool_log["render_calls"][-1] if _tool_log["render_calls"] else {"url": "", "description": ""}
    return VisualizationOutput(
        render_url=last_call["url"],
        scene_notes=[c["description"] for c in _tool_log["render_calls"]],
    )