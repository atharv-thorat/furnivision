# FurniVision — Build Plan

Say "build N" (for example "build 1" or "build 0B") and that step is built.

## How we work

- One step at a time. Each step ends with a check you can run ("Done when").
- Before any step that changes the database, take a database dump and a zip (README section 8).
- Stored style values stay `modern`, `scandinavian`, `industrial`, `traditional`. Friendly names are labels in the UI only.
- Furniture is never shrunk to fix a collision. The order is: move, rotate, rearrange neighbours, swap for a smaller item, drop and tell the user.
- Agents never edit source or calibration files at runtime. They save data (layouts) in the database.
- API keys live only in `backend/.env`, never in a web page.
- Claude Code implements backend steps in the repo and runs the backend, tests and browser checks. Claude in chat writes the spec and builds and tests the front-end pieces.
- Files marked **new** do not exist yet. Descriptions of files not yet opened (`pipeline.py`, `placement.py`, `schemas.py`, `planning_optimization.py`, `seed_furniture.py`, `db_models.py`, `design_material.py`, `room_intelligence.py`) are inferred and get confirmed when they are opened.

---

## Step 0: Prep (the app behaves the same)

**0A. Checkpoint**
- Database dump and project zip before schema changes. The dump and zip from 28 Sep cover the current state.
- Done when: the `.sql` and `.zip` exist and `unzip -tq` reports no errors.

**0B. Project context for Claude Code**
- Files: **`CLAUDE.md`** in the repo root. It holds the startup steps, the file map, the pitfalls we hit (ngrok skip-warning header, Docker down causes a 500, three.js `Box3` ignores `.visible`) and the check commands.
- Done when: a fresh Claude Code session can start the backend using only that file.

**0C. One model client for all agents**
- Choose the model per agent (local Qwen or Gemini). Force JSON-schema output, validate and repair it, retry on rate limits, and fall back to the local model.
- Files: `config.py`, `.env`, `.env.example`, **`agents/llm_client.py`**.
- Needs: a Gemini API key, which is optional. Local works without it.
- Done when: a test script gets valid JSON from both models and falls back to local when Gemini is off.

---

## Step 1: Style and collection (your first change)

- Add a `collection` column (`budget` or `standard`). Give each of the 9 Budget pieces its real style. Add friendly style labels in the UI. The over-budget fallback picks cheaper items by collection across styles, not by style.
- Files: `schema.sql`, `seed_furniture.py`, `db_models.py`, `catalog.py`, `planning_optimization.py`, `index.html`, `catalog-gallery.html`.
- Needs: `planning_optimization.py`, `seed_furniture.py`, `db_models.py`. Your decision on Budget Platform Bed's style (it was missing from your list). A check of the 8 styles judged from images.
- Done when: a Scandinavian request returns Scandinavian pieces, budget-collection pieces show up as cheaper alternatives, and an over-budget run still ends within budget.

## Step 2: Size rules

- Size each model by its physically fixed dimension (height for tables, chairs, lamps, nightstands, wardrobes and bookshelves; length for beds; width for sofas). Then shrink, never enlarge, to a plausible footprint per category. Rules live in one editable file.
- Files: **`ar_pages/category-rules.json`**, `ar-design.html`, `model-qa.html`.
- Done when: every dining table is about 75 cm tall, floor lamps are at most 55 cm across, and the QA page shows the same sizes as AR.

## Step 3: Model cleanup

- Finish the flagged (≠) pass in `model-qa.html`: turn 90° where hinted, hide stray meshes, use fit-inside where it helps, and tick needs-cleanup on wrong-kind assets. Replace about ten wrong-kind `.glb` files under the same filenames. Generate the 12 missing thumbnails. Re-export `model-calibration.json`.
- Files: `model-calibration.json`, `models_3d/`.
- Needs: you, for the QA pass and the replacement models.
- Done when: no item is flagged, or every flagged item is marked needs-cleanup.

## Step 4: Real sizes in the database

- Store each item's approved size in the database and return it from the catalog API.
- Files: `seed_furniture.py` or a SQL update, `db_models.py`, `catalog.py`.
- Needs: step 3.
- Done when: `/api/v1/catalog/furniture` returns sizes that match the QA page.

---

## Step 5: Walls in AR

- 5a: probe whether your phone reports vertical planes (a debug readout).
- 5b: mark the room corners by tapping the floor, and draw the wall lines.
- 5c: snap to detected walls when the phone provides them.
- 5d: save the room polygon and ceiling height with the project.
- Files: `ar-design.html` (or a new `ar-room.html`), `rooms.py`, `schemas.py`, `db_models.py`.
- Done when: four taps on your phone draw outlines that match the room, and the saved room reloads.

## Step 6: Doors, windows and owned furniture

- Form fields for doors, windows and furniture the user already owns (a box with its own size). Tap to mark openings in AR. Detect openings from photos using SegFormer's door and window labels. Save them with the room.
- Files: `index.html`, `rooms.py`, `room_intelligence.py`, `schemas.py`.
- Needs: step 5.
- Done when: the saved room record includes its openings and owned pieces.

---

## Step 7: Placement rules and checker

- Rules for the 9 categories in one data file. A checker for overlaps, walkway width, doors and windows, everything inside the walls, fronts facing the room, and a score. It has tests.
- Files: **`placement_rules.json`**, **`agents/layout_tools.py`**, **`scripts/test_layout_tools.py`**.
- Needs: steps 4, 5 and 6.
- Done when: the tests pass on hand-made good and bad layouts.

## Step 8: Layout agent

- The model proposes placements. The checker verifies. Violations are repaired down the ladder (move, rotate, rearrange, swap, drop). A "doesn't fit" request goes back to Planning & Optimization for a smaller item. `placement.py` stays as the fallback.
- Files: **`agents/layout.py`**, `pipeline.py`, `schemas.py`, `planning_optimization.py`, `placement.py`.
- Needs: steps 0C and 7.
- Done when: a sample room gets a valid layout, and a too-small room gets a swap or a clear message.

## Step 9: Save and serve layouts

- Save each layout with its design version and return it from the AR manifest.
- Files: `schema.sql`, `db_models.py`, `designs.py`.
- Done when: reopening a design shows the same layout.

## Step 10: 3D room view

- A new page, `room-view.html`. It shows a floor and walls sized to the saved room, and the furniture from the saved layout, using the calibrated models. You can orbit around it. It is linked from the results screen.
- Files: **`ar_pages/room-view.html`**, `index.html`.
- Needs: steps 3 and 9.
- Done when: positions, sizes and fronts in the view match the layout numbers.

## Step 11: AR "Arrange" button

- One tap places every item of the layout against the marked corners and lists anything that didn't fit.
- Files: `ar-design.html`, `index.html`.
- Needs: steps 5 and 9.
- Done when: on your phone, one tap places the whole design against the right walls.

---

## Step 12: Placement judge

- The backend draws a top-down picture of the layout. A judge model returns a score, a list of problems and suggested fixes. The layout agent applies them through the checker, with at most 3 rounds.
- Files: **`agents/judge.py`**, `layout.py`, `pipeline.py`.
- Needs: steps 0C and 8.
- Done when: a deliberately bad layout scores low and gets improved.

## Step 13: Evaluation harness

- One command runs about 30 sample rooms and prints a table: budget met, valid-layout rate, revisions used, seconds per agent. It compares the local model with Gemini as judge.
- Files: **`scripts/eval_rooms.py`**.
- Done when: the command produces the table.

---

## Step 14: Picture from the 3D room

- The 3D room view produces a depth image (default: the browser renders it and uploads it). The render server gets a scene mode that feeds the depth image to ControlNet. The render server script moves into the repo so it is versioned.
- Files: `room-view.html`, `visualization.py`, **`render_server/`**, routes.
- Needs: step 10.
- Done when: the generated image shows the same number of pieces in the same places as the layout.

## Step 15: Render critic

- SegFormer counts furniture in the picture and compares with the plan. An optional Gemini check judges the style. On a miss, it retries up to twice, changing the ControlNet strength, prompt or seed.
- Files: `visualization.py`, `pipeline.py`, render server verify endpoint.
- Needs: step 14.
- Done when: an image missing a piece triggers a retry.

---

## Step 16: Brief and refine chat

- Free text ("reading corner, dark wood, 40k") becomes constraints. After a result, "cheaper" or "swap the sofa" re-runs only the agents that need it, from saved state.
- Files: **`agents/brief_intake.py`**, **`agents/supervisor.py`**, `pipeline.py`, `routes/pipeline.py` (`/refine`), `index.html`.
- Needs: step 8.
- Done when: "make it cheaper" re-runs planning and layout and keeps the rest.

## Step 17: AR guide

- Voice or text commands ("move the sofa to the window wall") make the model call tools that the AR page runs.
- Files: **`agents/ar_guide.py`**, an assistant route, `ar-design.html`.
- Needs: steps 5 and 11.
- Done when: the command moves the sofa.

## Step 18: Asset-QA agent

- For a new `.glb`, it renders four views in a headless browser. A vision model proposes the front side, scale and stray meshes. You confirm only the flagged ones.
- Files: **`scripts/asset_qa_agent.py`**.
- Done when: its proposal on a new model matches what you would have picked.

## Step 19: Documentation

- README, `API_CONTRACT.md`, `CREDITS.md` placeholders, and the Word document (it wrongly says 54 catalog rows and 5 styles; the catalog has 45 rows and 4 style values).

---

## Not changing

- The stored style values.
- Catalog item names.
- The ngrok domain.
- The calibration JSON format, which is only extended.

## Decisions still open

- Gemini: whether your country is eligible for the free tier, and whether to use it (step 0C).
- The style of Budget Platform Bed (step 1).
- Which `.glb` files to replace (step 3).
- Where the depth image is made, browser or server (step 14).
