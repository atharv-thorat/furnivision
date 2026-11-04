from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.api.routes import projects, rooms, pipeline, designs, catalog

app = FastAPI(title="FurniVision API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/models_3d", StaticFiles(directory="models_3d"), name="models_3d")
app.mount("/ar", StaticFiles(directory="ar_pages"), name="ar_pages")


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(projects.router, prefix=settings.api_v1_prefix)
app.include_router(rooms.router, prefix=settings.api_v1_prefix)
app.include_router(pipeline.router, prefix=settings.api_v1_prefix)
app.include_router(designs.router, prefix=settings.api_v1_prefix)
app.include_router(catalog.router, prefix=settings.api_v1_prefix)
# WebSocket for live pipeline progress goes here once the job queue exists:
# @app.websocket(f"{settings.api_v1_prefix}/ws/projects/{{project_id}}")