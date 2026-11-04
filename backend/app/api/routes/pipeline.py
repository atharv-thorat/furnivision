from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from app.db.session import get_db
from app.models.db_models import Project, DesignVersion ,Room 
from app.agents.pipeline import graph
from app.agents.schemas import ManualRoomInput
from app.agents.placement import compute_placements
router = APIRouter(prefix="/projects/{project_id}/run", tags=["pipeline"])


class RunRequest(BaseModel):
    room_id: Optional[str] = None
    width_m: Optional[float] = None
    length_m: Optional[float] = None
    height_m: Optional[float] = None
    obstacles: List[str] = []
    notes: Optional[str] = None
    photo_path: Optional[str] = None
    user_style_pref: str
    budget_max: Optional[float] = None
    image_description: Optional[str] = None


@router.post("")
def trigger_run(project_id: str, req: RunRequest, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return {"error": "project not found"}

    budget_max = req.budget_max if req.budget_max is not None else (
        float(project.budget_max) if project.budget_max else None
    )
    if budget_max is None:
        return {"error": "budget_max not provided and no default set on project"}

    width_m, length_m, height_m = req.width_m, req.length_m, req.height_m
    obstacles, notes, photo_path = req.obstacles, req.notes, req.photo_path

    room = None
    if req.room_id:
        room = db.query(Room).filter(Room.id == req.room_id, Room.project_id == project_id).first()
        if not room:
            return {"error": "specified room_id not found for this project"}
    elif width_m is None or length_m is None or height_m is None:
        room = (
            db.query(Room)
            .filter(Room.project_id == project_id)
            .order_by(Room.created_at.desc())
            .first()
        )
        if not room:
            return {"error": "no room dimensions provided and no uploaded room found for this project"}

    if room:
        dims = room.dimensions or {}
        if width_m is None:
            width_m = dims.get("width_m")
        if length_m is None:
            length_m = dims.get("length_m")
        if height_m is None:
            height_m = dims.get("height_m")
        if not obstacles:
            obstacles = room.obstacles or []
        if not photo_path and room.image_urls:
            photo_path = room.image_urls[0]

    initial_state = {
        "manual_input": ManualRoomInput(
            width_m=width_m, length_m=length_m, height_m=height_m,
            obstacles=obstacles, notes=notes, photo_path=photo_path,
        ),
        "user_style_pref": req.user_style_pref,
        "budget_max": budget_max,
        "image_description": req.image_description,
        "room_data": None, "design_concepts": None,
        "furniture_plan": None, "visualization": None,
        "revision_count": 0, "status": "pending", "error": None,
    }

    final_state = graph.invoke(initial_state)

    if final_state.get("status") == "error":
        project.status = "error"
        db.commit()
        return {"status": "error", "error": final_state.get("error")}

    version_count = db.query(DesignVersion).filter(DesignVersion.project_id == project_id).count()
    plan = final_state.get("furniture_plan")
    viz = final_state.get("visualization")

    manifest = compute_placements(final_state["room_data"], plan) if plan else None

    version = DesignVersion(
        project_id=project_id,
        version_number=version_count + 1,
        design_concepts=final_state["design_concepts"].model_dump() if final_state.get("design_concepts") else None,
        furniture_plan=plan.model_dump() if plan else None,
        total_cost=plan.total_cost if plan else None,
        render_urls=[viz.render_url] if viz and viz.render_url and not viz.render_url.startswith("ERROR") else [],
        ar_scene_manifest=manifest,
    )
    db.add(version)
    project.status = "done"
    db.commit()
    db.refresh(version)

    return {
        "status": "done",
        "design_version_id": str(version.id),
        "version_number": version.version_number,
        "render_url": version.render_urls[0] if version.render_urls else None,
        "total_cost": float(version.total_cost) if version.total_cost else None,
        "revisions_used": final_state.get("revision_count", 0),
        "used_room_id": str(room.id) if room else None,
    }