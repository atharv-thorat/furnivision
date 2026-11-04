from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.db.session import get_db
from app.models.db_models import Project, Room

router = APIRouter(prefix="/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    name: str
    budget_max: Optional[float] = None
    style_prefs: Optional[dict] = None


@router.post("")
def create_project(req: CreateProjectRequest, db: Session = Depends(get_db)):
    project = Project(
        name=req.name,
        budget_max=req.budget_max,
        style_prefs=req.style_prefs or {},
        status="pending",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return {"id": str(project.id), "status": project.status}


@router.get("/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return {"error": "not found"}

    room = (
        db.query(Room)
        .filter(Room.project_id == project_id)
        .order_by(Room.created_at.desc())
        .first()
    )
    dims = (room.dimensions or {}) if room else {}
    room_data = {
        "width_m": dims.get("width_m"),
        "length_m": dims.get("length_m"),
        "height_m": dims.get("height_m"),
    } if room else None

    return {"id": str(project.id), "name": project.name, "status": project.status, "room": room_data}


@router.get("")
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.created_at.desc()).limit(20).all()
    return [{"id": str(p.id), "name": p.name, "status": p.status} for p in projects]