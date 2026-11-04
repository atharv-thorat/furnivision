from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from sqlalchemy import text
from app.agents.room_intelligence import _get_model
from app.agents.schemas import RoomData, DesignConcepts, FurniturePlan
from app.db.session import SessionLocal

_tool_log: dict = {"items": [], "budget_checks": []}
_revision_context: dict = {"revision_count": 0}


@tool
def search_catalog(category: str, style: str, max_price: float) -> list:
    """Search the furniture catalog for items in a category matching a style.
    Search each category ONCE only — do not repeat a search for a category
    you've already searched. Returns the cheapest available real options.
    Valid categories: bed, wardrobe, nightstand, sofa, coffee_table, dining_table,
    dining_chair, bookshelf, lamp."""
    db = SessionLocal()
    is_revision = _revision_context["revision_count"] > 0
    try:
        if is_revision:
            # Real fix (Build Plan step 1): prefer a real "budget collection"
            # item in the SAME style first, rather than immediately grabbing
            # the cheapest item in ANY style — that previously let a revision
            # mix, say, a Traditional bed with a Modern wardrobe. Only when
            # no budget-collection item shares this exact style do we fall
            # back to the original any-style cheapest search, kept as the
            # genuine last resort so a revision can still always find
            # *something* within budget.
            rows = db.execute(
                text("""
                    SELECT name, price, category, model_asset_url, dimensions
                    FROM furniture_items
                    WHERE category ILIKE :category
                    AND metadata->>'style' ILIKE :style
                    AND metadata->>'collection' = 'budget'
                    ORDER BY price ASC
                    LIMIT 1
                """),
                {"category": f"%{category}%", "style": f"%{style}%"},
            ).fetchall()
            if not rows:
                rows = db.execute(
                    text("""
                        SELECT name, price, category, model_asset_url, dimensions
                        FROM furniture_items
                        WHERE category ILIKE :category
                        ORDER BY price ASC
                        LIMIT 1
                    """),
                    {"category": f"%{category}%"},
                ).fetchall()
        else:
            rows = db.execute(
                text("""
                    SELECT name, price, category, model_asset_url, dimensions
                    FROM furniture_items
                    WHERE category ILIKE :category
                    AND metadata->>'style' ILIKE :style
                    ORDER BY price ASC
                    LIMIT 1
                """),
                {"category": f"%{category}%", "style": f"%{style}%"},
            ).fetchall()
        items = [
            {
                "name": r.name,
                "price": float(r.price),
                "category": r.category,
                "model_asset_url": r.model_asset_url,
                "dimensions": r.dimensions or {},
            }
            for r in rows
        ]
    finally:
        db.close()

    if not items:
        print(f"[Planning & Optimization] Searched '{category}' ({style}) -> no catalog match, using fallback estimate")
        items = [{
            "name": f"{style} {category} (no catalog match)",
            "price": round(30000 * 0.3, 2),
            "category": category,
            "model_asset_url": None,
            "dimensions": {},
        }]
    else:
        tag = " [cross-style fallback — cheaper alternative]" if is_revision else ""
        print(f"[Planning & Optimization] Searched '{category}' ({style}) -> {items[0]['name']} @ ₹{items[0]['price']:,.0f}{tag}")

    _tool_log["items"] = [i for i in _tool_log["items"] if i["category"] != category]
    _tool_log["items"].extend(items)
    return items


@tool
def check_budget_fit(item_prices: list, budget_max: float) -> str:
    """Check whether a list of item prices fits within the total budget.
    Call this exactly once, after you've searched all needed categories."""
    total = sum(item_prices)
    verdict = (
        f"Over budget: total {total} exceeds max {budget_max}."
        if total > budget_max
        else f"Within budget: total {total} of max {budget_max}."
    )
    status = "OVER BUDGET — will trigger a revision" if total > budget_max else "WITHIN BUDGET"
    print(f"[Planning & Optimization] Budget check: ₹{total:,.0f} / ₹{budget_max:,.0f} -> {status}")
    _tool_log["budget_checks"].append(verdict)
    return verdict


def propose_furniture_plan(room_data: RoomData, design: DesignConcepts, budget_max: float, revision_count: int =0) -> FurniturePlan:
    """Run the Planning & Optimization agent given room data, design concepts, and a budget."""
    _tool_log["items"].clear()
    _tool_log["budget_checks"].clear()
    _revision_context["revision_count"] = revision_count

    mode = f"REVISION #{revision_count} — searching cross-style for cheaper real items" if revision_count > 0 else "Initial pass — exact style match"
    print(f"[Planning & Optimization] {mode} | Room type: {room_data.notes or 'not specified'} | Style: {design.style} | Budget: ₹{budget_max:,.0f}")

    model = _get_model()
    agent = create_react_agent(
        model,
        tools=[search_catalog, check_budget_fit],
        state_modifier=(
            "You are the Planning & Optimization agent for FurniVision. Given "
            "room data, design concepts, and a budget: identify 2-3 furniture "
            "categories the room ACTUALLY needs, based strictly on the real "
            "room type given (e.g. a bedroom needs bed/wardrobe/nightstand — "
            "NEVER a sofa or dining table; a living room needs sofa/coffee_table "
            "— NEVER a bed). Call search_catalog EXACTLY ONCE per category — "
            "never repeat a search for a category you've already searched, "
            "even if the price seems high. After searching all needed "
            "categories, call check_budget_fit exactly once with the real "
            "prices you found. Once you've done that, you are finished — do "
            "not search further categories or styles."
        ),
    )

    try:
        agent.invoke(
            {
                "messages": [{
                    "role": "user",
                    "content": (
                        f"Room: {room_data.floor_area_m2}m2, room type/notes: {room_data.notes or 'not specified'}. "
                        f"Style: {design.style}, palette: {design.palette}. Budget max: {budget_max}."
                    ),
                }]
            },
            config={"recursion_limit": 15},
        )
    except Exception as e:
        if "recursion limit" in str(e).lower():
            print(f"[Planning & Optimization] Hit the recursion safety limit — proceeding with the {len(_tool_log['items'])} items found so far (fallback, not a crash).")
        else:
            raise

    total_cost = sum(i["price"] for i in _tool_log["items"])
    fits = total_cost <= budget_max
    print(f"[Planning & Optimization] Final plan: {len(_tool_log['items'])} items, ₹{total_cost:,.0f} total -> {'FITS' if fits else 'DOES NOT FIT'} budget")

    return FurniturePlan(
        items=list(_tool_log["items"]),
        total_cost=round(total_cost, 2),
        fits_budget=fits,
        notes=list(_tool_log["budget_checks"]) or [f"Budget check not completed by agent; computed total directly: {'within' if fits else 'over'} budget."],
    )
