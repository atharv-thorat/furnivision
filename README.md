# FurniVision

A four-agent AI interior design system. A room's dimensions and a budget go in; a priced furniture plan and an AI-generated render come out. The same real 3D catalog can be browsed and placed in the user's actual room with live WebXR AR on Android.

---

## 1. Quick start (every session)

Long-running processes each get their own terminal.

**Prerequisites**
- Docker Desktop and the `furnivision` conda env
- `backend/.env` and `backend/.env.llm`, copied from `.env.example` and `.env.llm.example`. Set your own database password.
- An Ollama server the backend can reach (model `qwen2.5:7b-instruct`), set in `OLLAMA_BASE_URL` and `LLM_LOCAL_BASE_URL`
- A render server (Stable Diffusion, port 8001). Its script is not in this repo.
- The 3D models, which are not in this repo (see `backend/models_3d/README.md`)

**1. Docker (Postgres on host port 5433, plus Redis, both bound to localhost)**
```bash
cd backend
docker compose up -d
docker compose ps        # both containers must show "Up"
```

**2. Point the backend at your render server**
```bash
sed -i '' 's|RENDER_SERVER_URL=.*|RENDER_SERVER_URL=https://<render-server-url>|' .env
```

**3. Backend.** Run it from `backend/`: the static mounts use relative paths.
```bash
conda activate furnivision
uvicorn app.main:app --reload
curl http://localhost:8000/health
```

**4. HTTPS tunnel** (only for testing on a phone)

The API has no authentication yet, so anyone with the tunnel URL can read and create projects. Only run a tunnel while you are testing, and add authentication before sharing it.
```bash
ngrok http 8000 --url=https://<your-ngrok-domain>
```

**5. Open the app**
```
https://<your-ngrok-domain>/ar/index.html
```
On the same machine, use `http://localhost:8000/ar/index.html`. AR needs Android, Chrome, and an ARCore-supported phone, over HTTPS.

**Notes**
- `model_asset_url` values in the database may contain an old LAN IP. This is harmless: the AR page keeps only the path and rewrites it to the current origin. `link_3d_models.py` only needs re-running if model files are added or renamed.
- `ar_pages/ar-design.html` uses the origin that served the page as its backend, so a new tunnel domain needs no code change.
- If `/api/v1/catalog/furniture` returns 500, the usual cause is a stopped Postgres container (`connection refused` on port 5433). Run `docker compose up -d`.

---

## 2. What it does

1. The user enters room size, style and budget in `index.html`, optionally with a room photo.
2. Four LangGraph agents run in sequence: Room Intelligence, Design & Material, Planning & Optimization, Visualization. If the plan is over budget, control loops back to Design & Material (capped at 2 revisions).
3. Planning & Optimization searches the real PostgreSQL catalog and totals real prices against the budget.
4. Visualization sends a scene description to the render server (Stable Diffusion, with SegFormer and MiDaS/ControlNet when a photo is given).
5. The results screen shows the render and a bill of furniture. "Browse Furniture" opens the catalog gallery, where any item opens directly in AR.

```
index.html   Home -> Choose Path -+- Design My Room -> form -> pipeline -> results -> Browse Furniture -+
                                  +- Browse & Place in AR -------------------------------------------+
                                                                                                      v
                             catalog-gallery.html (grid of all 45) -> ar-design.html?preselect=<item name>
```

---

## 3. File map

```
furnivision-1/
├── README.md
├── docs/
│   └── API_CONTRACT.md
├── backend/
│   ├── .env.example, .env.llm.example
│   ├── docker-compose.yml               # Postgres + Redis
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py                      # FastAPI app, routers, static mounts /models_3d and /ar
│   │   ├── config.py
│   │   ├── agents/
│   │   │   ├── pipeline.py              # LangGraph state machine and budget-revision routing
│   │   │   ├── room_intelligence.py     # agent 1
│   │   │   ├── design_material.py       # agent 2
│   │   │   ├── planning_optimization.py # agent 3, catalog search and budget check
│   │   │   ├── visualization.py         # agent 4, builds the scene prompt, calls the render server
│   │   │   ├── placement.py             # rule-based item positions/rotations for the AR manifest
│   │   │   └── schemas.py               # typed pipeline state
│   │   ├── api/routes/
│   │   │   ├── projects.py, rooms.py, pipeline.py, designs.py, catalog.py
│   │   ├── db/
│   │   │   ├── schema.sql, seed_furniture.py, link_3d_models.py, session.py
│   │   └── models/db_models.py          # SQLAlchemy models
│   ├── ar_pages/                        # served at /ar/<file>
│   │   ├── index.html                   # Home, Choose Path, Design flow
│   │   ├── catalog-gallery.html         # photo grid of all catalog items
│   │   ├── ar-design.html               # the WebXR AR engine
│   │   └── ar-catalog.html              # STALE pre-fix AR page, nothing links to it
│   ├── models_3d/                       # served at /models_3d/<file>; model files are not in this repo
│   ├── scripts/                         # test_room_intelligence, test_design_material,
│   │                                    # test_planning_optimization, test_visualization, test_pipeline
│   └── uploads/<project-uuid>/          # room photos uploaded through the app (runtime data, not in this repo)
└── app_flutter/                         # Flutter client (lib/main.dart)
```

`ar-design.html` takes two optional query modes:
- `?preselect=<item name>`: full catalog, that item pre-selected (used by the gallery)
- `?project=<id>&design=<id>`: only the items of one design via `/ar-manifest`. The current UI no longer links to this mode.

`app_flutter/`: an earlier native-AR attempt was blocked by a Sceneform namespace conflict, so AR moved to WebXR. Its `build/` output is very large and should not be zipped or committed.

---

## 4. API

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | liveness |
| `/api/v1/projects` | POST | create a project |
| `/api/v1/projects/{id}` | GET | project with its room |
| `/api/v1/projects/{id}/rooms` | POST | upload a room photo with dimensions |
| `/api/v1/projects/{id}/run` | POST | run the four-agent pipeline |
| `/api/v1/projects/{id}/designs/{design_id}` | GET | one design version in full |
| `/api/v1/projects/{id}/designs/{design_id}/ar-manifest` | GET | item names, positions, rotations, model URLs |
| `/api/v1/catalog/furniture` | GET | all 45 catalog items with real dimensions |

---

## 5. Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI, SQLAlchemy, Uvicorn |
| Data | PostgreSQL 16 and Redis in Docker |
| Agents | LangGraph, LangChain, Ollama (Qwen2.5 7B Instruct) |
| Vision | SegFormer (segmentation), MiDaS/DPT (depth) |
| Image generation | Stable Diffusion 1.5 with ControlNet depth inpainting |
| 3D / AR | Three.js, WebXR Device API, GLTFLoader, SkeletonUtils |
| Tunnel | ngrok |

---

## 6. Catalog and assets

- 45 catalog items: 9 categories (bed, wardrobe, nightstand, sofa, coffee_table, dining_table, dining_chair, bookshelf, lamp) with 5 items each. Four are named by style (Industrial, Modern, Scandinavian, Traditional). The fifth is a "Budget ..." variant tagged `style = scandinavian`. Every item has its own `.glb`.
- Screenshots exist for 33 of the 45 models. Missing (the gallery shows a category icon instead): `budget_platform_bed`, `industrial_bed_frame`, `modern_platform_bed`, `scandinavian_bookshelf`, `scandinavian_coffee_table`, `scandinavian_dining_table`, `scandinavian_nightstand`, `scandinavian_platform_bed`, `scandinavian_sofa`, `scandinavian_wardrobe`, `traditional_wardrobe`, `traditional_wooden_bed`.
- The model files and thumbnails are not published here while their licences are being confirmed.

---

## 7. Known issues

- **AR orientation:** the global rotation offset is 0°. Per-item corrections go in `ITEM_ROTATION_OVERRIDES` in `ar-design.html`, which is currently empty. Orientation of sofa, chair, bed, dining table and lamp after the last change is unconfirmed.
- **AR scale:** uniform scaling from each model's longest real dimension, an outlier-mesh exclusion (`computeReliableSize`, threshold 50x) and a 2.6 m cap on the largest dimension. Bad source `.glb` files can still misbehave.
- **Debug overlay:** `ar-design.html` still ships an on-screen debug panel (`debugPanel`). Remove it before a demo.
- **Placement is manual** (aim and tap). There is no room-geometry-aware auto placement.
- **Recommendation** is SQL filtering by style and budget. It is not room-size-aware, has no similarity search, and does not infer style from a photo.
- **Empty-room furnishing** by image generation is unreliable.
- **Not built:** eco-scoring, YOLOv8 object detection, OpenCV colour extraction.
- **Authentication:** the API has no login or access control yet, and CORS allows any origin. Do not expose it publicly as it stands.
- **Infrastructure:** a single-machine development setup. Docker containers stop between sessions.

---

## 8. Backup and restore

The zip holds code and assets only. Projects, design versions and catalog rows live in the Postgres volume, so back up the database separately.

```bash
# zip (from ~/Downloads)
zip -r furnivision-backup-$(date +%Y%m%d).zip furnivision-1 -x "*/.git/*" "*/app_flutter/build/*" "*/app_flutter/.dart_tool/*" "*/backend/uploads/*" "*/__pycache__/*" "*/.DS_Store"

# database dump (from backend/, Docker up)
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "${POSTGRES_DB:-$POSTGRES_USER}"' > furnivision-db-$(date +%Y%m%d).sql

# restore
docker compose up -d
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" "${POSTGRES_DB:-$POSTGRES_USER}"' < furnivision-db-YYYYMMDD.sql
```

Not covered by either: the render-server script and the Ollama setup.
