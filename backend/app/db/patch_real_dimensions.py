"""
One-time, idempotent data patch: real dimensions (Build Plan step 4).

What this does, and does NOT do:
  * Reads model-calibration.json (the file model-qa.html exports — the real,
    person-approved size of each catalog item) and writes each item's
    sizeM (in metres) into `dimensions` on the matching `furniture_items`
    row, converted to the same {width_cm, depth_cm, height_cm} shape the
    column already uses. This replaces the generic per-category placeholder
    numbers from seed_furniture.py with the measured size of the actual
    .glb file.
  * Only touches rows with model_asset_url IS NOT NULL (the 45 linked,
    real catalog items) and only a row whose name matches an item in the
    JSON. Everything else — price, metadata (style/collection), the 9
    unlinked rows — is untouched.
  * Skips any item whose calibration entry is not reviewed, or has no
    sizeM yet, or is marked needsCleanup (a flagged placeholder asset,
    about to be replaced — writing its current, known-wrong size to the
    database would be worse than leaving the generic placeholder there).
  * Is safe to run again later, after any of the pending asset
    replacements land: re-running after a new model-calibration.json
    export simply updates the rows whose approved size actually changed.

Usage (from backend/, same environment as the app):
    python app/db/patch_real_dimensions.py /path/to/model-calibration.json              # apply
    python app/db/patch_real_dimensions.py /path/to/model-calibration.json --dry-run    # show only
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/

from sqlalchemy import text  # noqa: E402

from app.db.session import engine  # noqa: E402


def to_dimensions_cm(size_m: dict) -> dict:
    """{"w":.., "d":.., "h":..} in metres -> {"width_cm":.., "depth_cm":.., "height_cm":..}, rounded to the nearest mm."""
    return {
        "width_cm": round(size_m["w"] * 100, 1),
        "depth_cm": round(size_m["d"] * 100, 1),
        "height_cm": round(size_m["h"] * 100, 1),
    }


def run(calibration_path: Path, dry_run: bool) -> int:
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    items = calibration.get("items", {})
    if not items:
        print(f"No items found in {calibration_path}. Nothing to do.")
        return 0

    with engine.begin() as conn:
        rows = {
            r.name: r
            for r in conn.execute(
                text("SELECT id, name, dimensions FROM furniture_items WHERE model_asset_url IS NOT NULL")
            ).fetchall()
        }

        planned, skipped = [], []
        for name, cal in items.items():
            row = rows.get(name)
            if row is None:
                skipped.append((name, "no matching catalog row (unlinked, or name mismatch)"))
                continue
            if not cal.get("reviewed"):
                skipped.append((name, "not reviewed yet in model-qa.html"))
                continue
            if cal.get("needsCleanup"):
                skipped.append((name, "needsCleanup is set — keeping the placeholder dims until the asset is replaced"))
                continue
            size_m = cal.get("sizeM")
            if not size_m:
                skipped.append((name, "reviewed, but no sizeM recorded"))
                continue

            new_dims = to_dimensions_cm(size_m)
            if row.dimensions == new_dims:
                continue  # already up to date
            planned.append((row.id, name, row.dimensions, new_dims))

        print(f"{len(items)} items in {calibration_path.name}; {len(planned)} row(s) need a dimensions update; "
              f"{len(skipped)} skipped.")
        for name, reason in skipped:
            print(f"  skip  {name!r}: {reason}")
        for _id, name, old, new in planned:
            print(f"  {name!r}: {old} -> {new}")

        if dry_run:
            print("\n--dry-run: no changes written.")
            return 0

        for _id, _name, _old, new in planned:
            conn.execute(
                text("UPDATE furniture_items SET dimensions = CAST(:dims AS JSONB) WHERE id = :id"),
                {"dims": json.dumps(new), "id": _id},
            )

        print(f"\nApplied {len(planned)} dimensions update(s).")
        return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("calibration_json", type=Path, help="path to model-calibration.json")
    ap.add_argument("--dry-run", action="store_true", help="show planned changes, write nothing")
    args = ap.parse_args()
    sys.exit(run(args.calibration_json, dry_run=args.dry_run))
