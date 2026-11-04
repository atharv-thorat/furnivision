from dotenv import load_dotenv
load_dotenv()

from app.agents.pipeline import graph
from app.agents.schemas import ManualRoomInput

if __name__ == "__main__":
    initial_state = {
        "manual_input": ManualRoomInput(
            width_m=4.2, length_m=3.6, height_m=2.6,
            obstacles=["window on north wall"],
            notes="Standard bedroom",
        ),
        "user_style_pref": "scandinavian",
        "budget_max": 30000,
        "room_data": None,
        "design_concepts": None,
        "furniture_plan": None,
        "visualization": None,
        "revision_count": 0,
        "status": "pending",
        "error": None,
    }

    final_state = graph.invoke(initial_state)

    print("Status:", final_state["status"])
    print("Revisions used:", final_state["revision_count"])

    if final_state.get("room_data"):
        print("\n--- Room Data ---")
        print(final_state["room_data"].model_dump_json(indent=2))
    if final_state.get("design_concepts"):
        print("\n--- Design Concepts ---")
        print(final_state["design_concepts"].model_dump_json(indent=2))
    if final_state.get("furniture_plan"):
        print("\n--- Furniture Plan ---")
        print(final_state["furniture_plan"].model_dump_json(indent=2))
    if final_state.get("visualization"):
        print("\n--- Visualization ---")
        print(final_state["visualization"].model_dump_json(indent=2))
    if final_state.get("error"):
        print("\n--- Error ---")
        print(final_state["error"])