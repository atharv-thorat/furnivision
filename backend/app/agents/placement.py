"""
Computes where each piece of furniture should sit in the room, in meters,
for the AR client to place. This is a deliberately simple heuristic —
line items up along the back wall, then wrap to the left wall once it
runs out of space — not real interior-design optimization. It's enough
to prove the AR manifest pipeline end to end; a smarter layout (avoiding
windows/doors, grouping by function) is a real future upgrade, not this.
"""


def compute_placements(room_data, furniture_plan) -> list:
    length_m = room_data.length_m  # back wall runs along this axis
    cursor = 0.0
    wall = "back"
    placements = []

    for item in furniture_plan.items:
        dims = item.get("dimensions") or {}
        width_m = (dims.get("width_cm") or 80) / 100
        depth_m = (dims.get("depth_cm") or 80) / 100

        if wall == "back" and cursor + width_m > length_m:
            wall = "left"
            cursor = 0.0

        if wall == "back":
            x, z, rotation_deg = cursor + width_m / 2, depth_m / 2, 0
        else:
            x, z, rotation_deg = depth_m / 2, cursor + width_m / 2, 90

        cursor += width_m

        placements.append({
            "name": item.get("name"),
            "model_asset_url": item.get("model_asset_url"),
            "position": {"x": round(x, 2), "y": 0.0, "z": round(z, 2)},
            "rotation_deg": rotation_deg,
        })

    return placements