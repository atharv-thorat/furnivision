"""
One-time, idempotent data patch: style + collection (Build Plan step 1).

What this does, and does NOT do:
  * Patches `metadata` on the 45 catalog rows that already have a model_asset_url
    (the ones the real app can place in AR). Leaves everything else — price,
    dimensions, model_asset_url, the 9 unlinked "Budget Modern/Industrial/
    Traditional ..." rows with no .glb — completely untouched.
  * Adds `collection`: "budget" on the 9 "Budget ..." items, "standard" on the
    other 36. This does not change any stored `style` value except the ones
    listed in STYLE_CORRECTIONS below.
  * Re-tags 8 of the 9 "Budget ..." items to their real visual style, per a
    style classification. "Budget Coffee Table" was already
    tagged scandinavian and keeps that tag. "Budget Platform Bed" style was
    not confirmed, so its style is left as-is and it is flagged
    needs_review: true in its own metadata instead of being guessed.
  * Uses Postgres's jsonb `||` operator, which merges and overwrites only the
    named keys — every other key already in `metadata` survives untouched.
  * Is safe to run more than once: re-running produces the same end state and
    reports 0 changed rows the second time.

Usage (from backend/, same environment as the app):
    python app/db/patch_style_collection.py              # apply
    python app/db/patch_style_collection.py --dry-run     # show what would change, write nothing
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/

from sqlalchemy import text  # noqa: E402

from app.db.session import engine  # noqa: E402

# Real visual style for each "Budget ..." item, from a classification pass
# over the actual catalog photos. "Budget Platform Bed" is deliberately
# excluded here: its style was never confirmed, so this script does not
# guess it (see needs_review below).
STYLE_CORRECTIONS = {
    "Budget Bookshelf": "modern",
    "Budget Dining Chair": "traditional",
    "Budget Dining Table": "traditional",
    "Budget Floor Lamp": "industrial",
    "Budget Nightstand": "modern",
    "Budget Sofa": "modern",
    "Budget Wardrobe": "modern",
    # "Budget Coffee Table" was already "scandinavian" and matches the
    # classification, so it is not listed here — nothing to correct.
}

NEEDS_REVIEW = {"Budget Platform Bed": "style not visually confirmed; left as-is"}

# Every real "Budget ..." catalog item (whether its style changes or not) —
# this is the full set that gets collection: "budget". Everything else
# linked gets collection: "standard".
BUDGET_ITEM_NAMES = {
    "Budget Bookshelf", "Budget Coffee Table", "Budget Dining Chair", "Budget Dining Table",
    "Budget Floor Lamp", "Budget Nightstand", "Budget Platform Bed", "Budget Sofa", "Budget Wardrobe",
}


def _row_summary(row) -> str:
    meta = row.metadata_ or {}
    return f"{row.name!r}: style={meta.get('style')!r} collection={meta.get('collection')!r}"


def run(dry_run: bool) -> int:
    with engine.begin() as conn:
        rows = conn.execute(
            text("""
                SELECT id, name, metadata AS metadata_
                FROM furniture_items
                WHERE model_asset_url IS NOT NULL
                ORDER BY name
            """)
        ).fetchall()

        if not rows:
            print("No linked catalog rows found (model_asset_url IS NOT NULL). Nothing to do.")
            return 0

        planned = []
        for r in rows:
            current = dict(r.metadata_ or {})
            patch: dict = {}

            collection = "budget" if r.name in BUDGET_ITEM_NAMES else "standard"
            if current.get("collection") != collection:
                patch["collection"] = collection

            new_style = STYLE_CORRECTIONS.get(r.name)
            if new_style and current.get("style") != new_style:
                patch["style"] = new_style

            if r.name in NEEDS_REVIEW and current.get("needs_review") is not True:
                patch["needs_review"] = True
                patch["needs_review_note"] = NEEDS_REVIEW[r.name]

            if patch:
                planned.append((r.id, r.name, current, patch))

        print(f"{len(rows)} linked catalog rows checked; {len(planned)} need a change.")
        for _id, name, current, patch in planned:
            after = {**current, **patch}
            print(f"  {name!r}: style {current.get('style')!r} -> {after.get('style')!r}"
                  f" | collection {current.get('collection')!r} -> {after.get('collection')!r}"
                  f"{' | needs_review=True' if patch.get('needs_review') else ''}")

        if dry_run:
            print("\n--dry-run: no changes written.")
            return 0

        for _id, _name, _current, patch in planned:
            conn.execute(
                text("UPDATE furniture_items SET metadata = metadata || CAST(:patch AS JSONB) WHERE id = :id"),
                {"patch": json.dumps(patch), "id": _id},
            )

        verify = conn.execute(
            text("SELECT id, name, metadata AS metadata_ FROM furniture_items WHERE model_asset_url IS NOT NULL ORDER BY name")
        ).fetchall()
        by_collection = {}
        for r in verify:
            c = (r.metadata_ or {}).get("collection", "(none)")
            by_collection[c] = by_collection.get(c, 0) + 1

        print(f"\nApplied {len(planned)} change(s). Collection counts now: {by_collection}")
        flagged = [r.name for r in verify if (r.metadata_ or {}).get("needs_review")]
        if flagged:
            print(f"Flagged for a manual style check: {flagged}")
        return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="show planned changes, write nothing")
    args = ap.parse_args()
    sys.exit(run(dry_run=args.dry_run))
