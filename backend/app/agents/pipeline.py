"""
FurniVision — the real LangGraph pipeline, wiring together the four
proven agent functions with a feedback loop: if Planning & Optimization
can't make the budget work, it routes back to Design & Material for a
revision, capped at MAX_REVISIONS to avoid an infinite loop.
"""

from typing import TypedDict, Optional, Literal
from langgraph.graph import StateGraph, END
from app.agents.placement import compute_placements
from app.agents.schemas import (
    ManualRoomInput, RoomData, DesignConcepts, FurniturePlan, VisualizationOutput,
)
from app.agents.room_intelligence import analyze_manual_room_input
from app.agents.design_material import propose_design
from app.agents.planning_optimization import propose_furniture_plan
from app.agents.visualization import visualize_design

STYLE_PROMPT_HINTS = {
    "scandinavian": "light oak and pale birch wood, soft white and dove-grey fabric, natural linen, minimal clean lines, airy and bright, morning daylight",
    "modern": "matte black and charcoal grey surfaces, brushed steel accents, deep navy and slate fabric, sharp geometric lines, dramatic side lighting",
    "industrial": "dark walnut and raw wood, black leather, exposed matte metal fixtures, weathered concrete textures, warm amber lighting",
    "traditional": "rich mahogany wood, deep burgundy and forest green fabric, ornate brass accents, classic carved details, warm golden lighting",
}
MAX_REVISIONS = 2


class FurniVisionState(TypedDict):
    manual_input: ManualRoomInput
    user_style_pref: str
    budget_max: float
    image_description: Optional[str]

    room_data: Optional[RoomData]
    design_concepts: Optional[DesignConcepts]
    furniture_plan: Optional[FurniturePlan]
    visualization: Optional[VisualizationOutput]

    revision_count: int
    status: Literal["pending", "analyzing_room", "designing", "planning", "rendering", "done", "error"]
    error: Optional[str]


def room_intelligence_node(state: FurniVisionState) -> dict:
    try:
        room_data = analyze_manual_room_input(state["manual_input"])
        return {"room_data": room_data, "status": "designing"}
    except Exception as e:
        return {"error": f"[room_intelligence] {e}", "status": "error"}


def design_material_node(state: FurniVisionState) -> dict:
    try:
        design = propose_design(state["room_data"], state["user_style_pref"])
        return {"design_concepts": design, "status": "planning"}
    except Exception as e:
        return {"error": f"[design_material] {e}", "status": "error"}


def planning_optimization_node(state: FurniVisionState) -> dict:
    try:
        plan = propose_furniture_plan(
            state["room_data"],
            state["design_concepts"],
            state["budget_max"],
            revision_count=state.get("revision_count", 0),
        )
        return {"furniture_plan": plan, "status": "rendering"}
    except Exception as e:
        return {"error": f"[planning_optimization] {e}", "status": "error"}
STYLE_PROMPT_HINTS = {
    "scandinavian": "light oak and pale birch wood, soft white and dove-grey fabric, natural linen, minimal clean lines, airy and bright, morning daylight",
    "modern": "matte black and charcoal grey surfaces, brushed steel accents, deep navy and slate fabric, sharp geometric lines, dramatic side lighting",
    "industrial": "dark walnut and raw wood, black leather, exposed matte metal fixtures, weathered concrete textures, warm amber lighting",
    "traditional": "rich mahogany wood, deep burgundy and forest green fabric, ornate brass accents, classic carved details, warm golden lighting",
}

def render_visualization_node(state: FurniVisionState) -> dict:
    try:
        viz = visualize_design(
            state["room_data"], state["furniture_plan"],
            state.get("image_description"), state.get("design_concepts"),
        )
        return {"visualization": viz, "status": "done"}
    except Exception as e:
        return {"error": f"[render_visualization] {e}", "status": "error"}


def prepare_revision_node(state: FurniVisionState) -> dict:
    """Bumps the revision counter before looping back to Design & Material."""
    return {"revision_count": state.get("revision_count", 0) + 1, "status": "designing"}


def error_handler_node(state: FurniVisionState) -> dict:
    return {"status": "error"}


def route_after_room_intelligence(state: FurniVisionState) -> str:
    return "error_handler" if state.get("status") == "error" else "design_material"


def route_after_design_material(state: FurniVisionState) -> str:
    return "error_handler" if state.get("status") == "error" else "planning_optimization"


def route_after_planning(state: FurniVisionState) -> str:
    if state.get("status") == "error":
        return "error_handler"
    plan = state.get("furniture_plan")
    revision_count = state.get("revision_count", 0)
    if plan and not plan.fits_budget and revision_count < MAX_REVISIONS:
        return "revise_design"
    return "render_visualization"


builder = StateGraph(FurniVisionState)
builder.add_node("room_intelligence", room_intelligence_node)
builder.add_node("design_material", design_material_node)
builder.add_node("planning_optimization", planning_optimization_node)
builder.add_node("render_visualization", render_visualization_node)
builder.add_node("prepare_revision", prepare_revision_node)
builder.add_node("error_handler", error_handler_node)

builder.set_entry_point("room_intelligence")

builder.add_conditional_edges("room_intelligence", route_after_room_intelligence, {
    "design_material": "design_material",
    "error_handler": "error_handler",
})
builder.add_conditional_edges("design_material", route_after_design_material, {
    "planning_optimization": "planning_optimization",
    "error_handler": "error_handler",
})
builder.add_conditional_edges("planning_optimization", route_after_planning, {
    "render_visualization": "render_visualization",
    "revise_design": "prepare_revision",
    "error_handler": "error_handler",
})
builder.add_edge("prepare_revision", "design_material")
builder.add_edge("render_visualization", END)
builder.add_edge("error_handler", END)

graph = builder.compile()