from dotenv import load_dotenv
load_dotenv()

from app.agents.room_intelligence import analyze_manual_room_input
from app.agents.schemas import ManualRoomInput

if __name__ == "__main__":
    test_input = ManualRoomInput(
        width_m=4.2,
        length_m=3.6,
        height_m=1.4,  # deliberately unrealistic — should trigger flag_concern
        obstacles=["window on north wall", "door on east wall"],
        notes="Standard bedroom",
    )
    result = analyze_manual_room_input(test_input)
    print(result.model_dump_json(indent=2))