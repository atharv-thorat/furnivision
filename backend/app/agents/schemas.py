from pydantic import BaseModel, Field
from typing import Optional, List


class ManualRoomInput(BaseModel):
    width_m: float
    length_m: float
    height_m: float
    obstacles: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    photo_path: Optional[str] = None  # NEW — path to the user's uploaded room photo


class RoomData(BaseModel):
    width_m: float
    length_m: float
    height_m: float
    floor_area_m2: float
    obstacles: List[str]
    warnings: List[str] = Field(default_factory=list)
    photo_path: Optional[str] = None  # NEW — carried forward so Visualization can use it

class DesignConcepts(BaseModel):
    style: str
    palette: dict

class FurniturePlan(BaseModel):
    items: list[dict]
    total_cost: float
    fits_budget: bool
    notes: list[str] = Field(default_factory=list)

class VisualizationOutput(BaseModel):
    render_url: str
    scene_notes: list[str] = Field(default_factory=list)

class RoomData(BaseModel):
    width_m: float
    length_m: float
    height_m: float
    floor_area_m2: float
    obstacles: List[str]
    warnings: List[str] = Field(default_factory=list)
    photo_path: Optional[str] = None
    notes: Optional[str] = None  # NEW