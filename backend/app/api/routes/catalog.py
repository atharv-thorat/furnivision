from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.session import get_db

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/furniture")
def list_furniture(db: Session = Depends(get_db)):
    """Real, full furniture catalog — every item with a linked 3D model,
    for the AR catalog selector. Read-only, additive endpoint; doesn't
    touch the existing pipeline/design routes at all."""
    rows = db.execute(
        text("""
            SELECT name, category, price, model_asset_url, dimensions,
                   metadata->>'style' AS style,
                   metadata->>'collection' AS collection
            FROM furniture_items
            WHERE model_asset_url IS NOT NULL
            ORDER BY category, style, price
        """)
    ).fetchall()
    return {
        "items": [
            {
                "name": r.name,
                "category": r.category,
                "style": r.style,
                "collection": r.collection,
                "price": float(r.price) if r.price is not None else None,
                "model_asset_url": r.model_asset_url,
                "dimensions": r.dimensions or {},
            }
            for r in rows
        ]
    }
