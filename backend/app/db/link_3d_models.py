import os
import re
from sqlalchemy import text
from app.db.session import engine

MODELS_DIR = "models_3d"
BASE_URL = "http://172.10.1.23:8000/models_3d"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def link_models():
    if not os.path.isdir(MODELS_DIR):
        print(f"No {MODELS_DIR} folder found — nothing to link.")
        return

    files = [f for f in os.listdir(MODELS_DIR) if f.endswith((".glb", ".gltf"))]
    print(f"Found {len(files)} model file(s) in {MODELS_DIR}/")

    with engine.begin() as conn:
        rows = conn.execute(text("SELECT id, name FROM furniture_items")).fetchall()
        by_slug = {slugify(r.name): r.id for r in rows}

        linked = 0
        for filename in files:
            file_slug = filename.rsplit(".", 1)[0]
            item_id = by_slug.get(file_slug)
            if item_id:
                conn.execute(
                    text("UPDATE furniture_items SET model_asset_url = :url WHERE id = :id"),
                    {"url": f"{BASE_URL}/{filename}", "id": item_id},
                )
                linked += 1
                print(f"  Linked: {filename} -> {file_slug}")
            else:
                print(f"  No matching catalog item for: {filename} (expected slug: {file_slug!r})")

    print(f"Linked {linked} of {len(files)} files.")


if __name__ == "__main__":
    link_models()
