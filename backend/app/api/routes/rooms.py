import os
import uuid as uuid_lib
import json
from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Optional
from app.db.session import get_db
from app.models.db_models import Room

router = APIRouter(prefix="/projects/{project_id}/rooms", tags=["rooms"])

UPLOAD_DIR = "uploads"


@router.post("")
def create_room(
    project_id: str,
    width_m: float = Form(...),
    length_m: float = Form(...),
    height_m: float = Form(...),
    obstacles: str = Form("[]"),  # JSON-encoded list, e.g. '["window on north wall"]'
    photo: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    image_urls = []
    if photo:
        project_dir = os.path.join(UPLOAD_DIR, project_id)
        os.makedirs(project_dir, exist_ok=True)
        filename = f"{uuid_lib.uuid4().hex}_{photo.filename}"
        file_path = os.path.join(project_dir, filename)
        with open(file_path, "wb") as f:
            f.write(photo.file.read())
        image_urls = [file_path]

    try:
        obstacles_list = json.loads(obstacles)
    except (json.JSONDecodeError, TypeError):
        obstacles_list = []

    room = Room(
        project_id=project_id,
        image_urls=image_urls,
        dimensions={"width_m": width_m, "length_m": length_m, "height_m": height_m},
        obstacles=obstacles_list,
    )
    db.add(room)
    db.commit()
    db.refresh(room)

    return {
        "id": str(room.id),
        "image_urls": room.image_urls,
        "dimensions": room.dimensions,
        "obstacles": room.obstacles,
    }