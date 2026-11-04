import uuid
from sqlalchemy import Column, String, Numeric, TIMESTAMP, ForeignKey, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=True)
    name = Column(String, nullable=False)
    budget_max = Column(Numeric(10, 2))
    style_prefs = Column(JSONB, default={})
    status = Column(String, nullable=False, default="pending")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class DesignVersion(Base):
    __tablename__ = "design_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    design_concepts = Column(JSONB)
    furniture_plan = Column(JSONB)
    total_cost = Column(Numeric(10, 2))
    render_urls = Column(ARRAY(String), default=[])
    ar_scene_manifest = Column(JSONB)  # NEW
    is_favorite = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

class Room(Base):
    __tablename__ = "rooms"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    image_urls = Column(ARRAY(String), default=[])
    dimensions = Column(JSONB)
    obstacles = Column(JSONB, default=[])
    detected_style = Column(String)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())