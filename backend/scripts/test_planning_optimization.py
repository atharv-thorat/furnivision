from dotenv import load_dotenv
load_dotenv()

from app.agents.room_intelligence import analyze_manual_room_input
from app.agents.design_material import propose_design
from app.agents.planning_optimization import propose_furniture_plan
from app.agents.schemas import ManualRoomInput

if __name__ == "__main__":
    room_input = ManualRoomInput(
        width_m=4.2, length_m=3.6, height_m=2.6,
        obstacles=["window on north wall"],
        notes="Standard bedroom",
    )
    room_data = analyze_manual_room_input(room_input)
    design = propose_design(room_data, user_style_pref="scandinavian")
    plan = propose_furniture_plan(room_data, design, budget_max=30000)
    print(plan.model_dump_json(indent=2))