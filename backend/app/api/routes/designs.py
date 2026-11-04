from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.db.session import get_db
from app.models.db_models import DesignVersion

router = APIRouter(prefix="/projects/{project_id}/designs", tags=["designs"])


@router.get("")
def list_designs(project_id: str, db: Session = Depends(get_db)):
    versions = (
        db.query(DesignVersion)
        .filter(DesignVersion.project_id == project_id)
        .order_by(DesignVersion.version_number.desc())
        .all()
    )
    return [
        {
            "id": str(v.id),
            "version_number": v.version_number,
            "total_cost": float(v.total_cost) if v.total_cost else None,
            "render_urls": v.render_urls,
            "is_favorite": v.is_favorite,
        }
        for v in versions
    ]


@router.get("/{version_id}")
def get_design(project_id: str, version_id: str, db: Session = Depends(get_db)):
    version = db.query(DesignVersion).filter(DesignVersion.id == version_id).first()
    if not version:
        return {"error": "not found"}
    return {
        "id": str(version.id),
        "version_number": version.version_number,
        "design_concepts": version.design_concepts,
        "furniture_plan": version.furniture_plan,
        "total_cost": float(version.total_cost) if version.total_cost else None,
        "render_urls": version.render_urls,
        "is_favorite": version.is_favorite,
    }


class FavoriteRequest(BaseModel):
    is_favorite: bool = True


@router.post("/{version_id}/favorite")
def favorite_design(project_id: str, version_id: str, req: FavoriteRequest, db: Session = Depends(get_db)):
    version = db.query(DesignVersion).filter(DesignVersion.id == version_id).first()
    if not version:
        return {"error": "not found"}
    version.is_favorite = req.is_favorite
    db.commit()
    return {"id": str(version.id), "is_favorite": version.is_favorite}
@router.get("/{version_id}/ar-manifest")
def get_ar_manifest(project_id: str, version_id: str, db: Session = Depends(get_db)):
    version = db.query(DesignVersion).filter(DesignVersion.id == version_id).first()
    if not version:
        return {"error": "not found"}
    return {
        "design_version_id": str(version.id),
        "items": version.ar_scene_manifest or [],
    }