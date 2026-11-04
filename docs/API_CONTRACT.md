# FurniVision API contract (draft v1)

Base URL: `/api/v1`
Auth: Bearer JWT on every route except `/auth/*`

Design note: project creation and room upload are synchronous (fast).
Triggering the agent pipeline is asynchronous — it kicks off a background
job (Celery/RQ worker calling `graph.invoke(...)`) and the client polls or
listens on the WebSocket for progress, since a full pass through all four
agents can take anywhere from seconds to a couple of minutes depending on
rendering load.

---

## Projects

### `POST /projects`
Create a new project.

Request:
```json
{ "name": "Living room refresh", "budget_max": 50000, "style_prefs": { "style": "scandinavian" } }
```
Response `201`:
```json
{ "id": "uuid", "status": "pending", "created_at": "..." }
```

### `GET /projects/{project_id}`
Returns project details, current `status`, and latest `design_version` summary if one exists.

### `GET /projects`
List the current user's projects (paginated: `?page=1&limit=20`).

---

## Rooms

### `POST /projects/{project_id}/rooms`
Upload room photos (multipart form) and any manual measurements the user provides.

Response `201`:
```json
{ "id": "uuid", "image_urls": ["..."], "status": "uploaded" }
```

---

## Pipeline execution

### `POST /projects/{project_id}/run`
Triggers the LangGraph pipeline. Returns immediately with a job reference;
does not block for the full run.

Response `202`:
```json
{ "job_id": "uuid", "status": "analyzing_room" }
```

### `GET /projects/{project_id}/run/{job_id}`
Poll for pipeline status (fallback for clients not using the WebSocket).

Response `200`:
```json
{
  "job_id": "uuid",
  "status": "planning",
  "current_agent": "planning_optimization",
  "progress": 0.6
}
```

### `WS /ws/projects/{project_id}`
Real-time event stream while a job runs. Message shape:
```json
{ "event": "agent_started",  "agent": "design_material" }
{ "event": "agent_completed","agent": "design_material", "summary": {"...": "..."} }
{ "event": "pipeline_done",  "design_version_id": "uuid" }
{ "event": "pipeline_error", "agent": "planning_optimization", "error": "..." }
```
This is what lets the UI show "Room Intelligence → Design & Material →
Planning → Visualization" as a live progress trail rather than one long spinner.

---

## Design versions

### `GET /projects/{project_id}/designs`
List all generated design versions for a project (for comparison/history).

### `GET /projects/{project_id}/designs/{version_id}`
Full detail: design concepts, furniture plan, placements, total cost, render URLs.

### `POST /projects/{project_id}/designs/{version_id}/favorite`
Mark a version as the favorite. Body: `{ "is_favorite": true }`.

---

## Catalog (used internally by the Planning agent, also exposed for manual browsing)

### `GET /furniture?category=sofa&max_price=15000`
### `GET /materials?category=fabric`

---

## Error shape (all endpoints)
```json
{ "error": { "code": "ROOM_ANALYSIS_FAILED", "message": "..." } }
```

## Decisions (locked)
- **Versioning**: yes, `/api/v1/...` from day one — matters more than usual
  here because the Android build lags behind backend deploys.
- **Partial re-runs**: supported. `POST .../run` accepts an optional
  `{"start_from": "<agent_name>", "parent_version_id": "<uuid>"}` — the
  orchestrator resumes from that agent, inheriting earlier state from the
  named parent version instead of always running all four agents.
- **Auth**: Firebase Authentication (shared across Flutter web + Android).
  The backend verifies the Firebase ID token on every request instead of
  issuing its own JWTs.

## AR handoff (new)

### `GET /projects/{project_id}/designs/{version_id}/ar-manifest`
Returns the `ar_scene_manifest` for a design version: a list of
`{furniture_item_id, model_asset_url, position, rotation}` objects. This is
what the Android client's ARCore session loads to place each 3D model at
true scale on the detected floor plane. Rendering itself happens entirely
on-device in real time — this endpoint only supplies the placement data.
