from sqlalchemy import text
from app.db.session import engine
import json

# (name, category, price_inr, style, width_cm, depth_cm, height_cm)
FURNITURE_CATALOG = [
    # bed
    ("Scandinavian Platform Bed", "bed", 18000, "scandinavian", 160, 200, 40),
    ("Modern Platform Bed", "bed", 22000, "modern", 160, 200, 35),
    ("Industrial Bed Frame", "bed", 20000, "industrial", 160, 200, 45),
    ("Budget Platform Bed", "bed", 9000, "scandinavian", 150, 195, 35),
    ("Traditional Wooden Bed", "bed", 25000, "traditional", 165, 205, 50),

    # wardrobe
    ("Scandinavian Wardrobe", "wardrobe", 15000, "scandinavian", 100, 60, 200),
    ("Modern Wardrobe", "wardrobe", 19000, "modern", 120, 60, 210),
    ("Industrial Wardrobe", "wardrobe", 17000, "industrial", 110, 60, 200),
    ("Budget Wardrobe", "wardrobe", 7500, "scandinavian", 90, 55, 190),
    ("Traditional Wardrobe", "wardrobe", 21000, "traditional", 130, 65, 215),

    # nightstand
    ("Scandinavian Nightstand", "nightstand", 4500, "scandinavian", 45, 40, 55),
    ("Modern Nightstand", "nightstand", 5500, "modern", 50, 40, 50),
    ("Industrial Nightstand", "nightstand", 5000, "industrial", 45, 40, 55),
    ("Budget Nightstand", "nightstand", 1800, "scandinavian", 40, 35, 50),
    ("Traditional Nightstand", "nightstand", 6000, "traditional", 48, 42, 58),

    # sofa
    ("Scandinavian Sofa", "sofa", 28000, "scandinavian", 210, 90, 85),
    ("Modern Sofa", "sofa", 32000, "modern", 220, 95, 80),
    ("Industrial Leather Sofa", "sofa", 35000, "industrial", 210, 90, 80),
    ("Budget Sofa", "sofa", 15000, "scandinavian", 195, 85, 80),
    ("Traditional Sofa", "sofa", 30000, "traditional", 215, 92, 88),

    # coffee_table
    ("Scandinavian Coffee Table", "coffee_table", 8000, "scandinavian", 100, 50, 40),
    ("Modern Coffee Table", "coffee_table", 9500, "modern", 110, 55, 38),
    ("Industrial Coffee Table", "coffee_table", 7500, "industrial", 100, 55, 40),
    ("Budget Coffee Table", "coffee_table", 4000, "scandinavian", 90, 45, 38),
    ("Traditional Coffee Table", "coffee_table", 9000, "traditional", 105, 52, 42),

    # dining_table
    ("Scandinavian Dining Table", "dining_table", 16000, "scandinavian", 150, 90, 75),
    ("Modern Dining Table", "dining_table", 21000, "modern", 160, 90, 75),
    ("Industrial Dining Table", "dining_table", 19000, "industrial", 155, 90, 75),
    ("Budget Dining Table", "dining_table", 9000, "scandinavian", 140, 85, 75),
    ("Traditional Dining Table", "dining_table", 24000, "traditional", 170, 95, 76),

    # dining_chair
    ("Scandinavian Dining Chair", "dining_chair", 4200, "scandinavian", 45, 50, 85),
    ("Modern Dining Chair", "dining_chair", 5000, "modern", 45, 52, 88),
    ("Industrial Dining Chair", "dining_chair", 4500, "industrial", 44, 50, 86),
    ("Budget Dining Chair", "dining_chair", 2000, "scandinavian", 42, 48, 84),
    ("Traditional Dining Chair", "dining_chair", 5500, "traditional", 46, 53, 90),

    # bookshelf
    ("Scandinavian Bookshelf", "bookshelf", 9000, "scandinavian", 80, 30, 180),
    ("Modern Bookshelf", "bookshelf", 10000, "modern", 85, 32, 185),
    ("Industrial Bookshelf", "bookshelf", 11000, "industrial", 90, 35, 190),
    ("Budget Bookshelf", "bookshelf", 5000, "scandinavian", 75, 28, 175),
    ("Traditional Bookshelf", "bookshelf", 12000, "traditional", 95, 36, 195),

    # lamp
    ("Scandinavian Floor Lamp", "lamp", 3500, "scandinavian", 30, 30, 150),
    ("Modern Floor Lamp", "lamp", 3800, "modern", 32, 32, 155),
    ("Industrial Floor Lamp", "lamp", 4200, "industrial", 35, 35, 160),
    ("Budget Floor Lamp", "lamp", 1500, "scandinavian", 28, 28, 145),
    ("Traditional Floor Lamp", "lamp", 4500, "traditional", 33, 33, 158),

    ("Budget Modern Bed", "bed", 10000, "modern", 150, 195, 35),
    ("Budget Modern Wardrobe", "wardrobe", 8500, "modern", 95, 55, 195),
    ("Budget Modern Nightstand", "nightstand", 2200, "modern", 42, 36, 48),

    ("Budget Industrial Bed", "bed", 9500, "industrial", 150, 195, 40),
    ("Budget Industrial Wardrobe", "wardrobe", 8000, "industrial", 95, 55, 190),
    ("Budget Industrial Nightstand", "nightstand", 2000, "industrial", 42, 36, 50),

    ("Budget Traditional Bed", "bed", 11000, "traditional", 155, 198, 45),
    ("Budget Traditional Wardrobe", "wardrobe", 9500, "traditional", 100, 58, 200),
    ("Budget Traditional Nightstand", "nightstand", 2500, "traditional", 44, 38, 52),
]


def seed():
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM furniture_items"))  # clean slate on re-run
        for name, category, price, style, w, d, h in FURNITURE_CATALOG:
            conn.execute(
                text("""
                    INSERT INTO furniture_items (name, category, price, dimensions, metadata)
                    VALUES (:name, :category, :price, :dimensions, :metadata)
                """),
                {
                    "name": name,
                    "category": category,
                    "price": price,
                    "dimensions": json.dumps({"width_cm": w, "depth_cm": d, "height_cm": h}),
                    "metadata": json.dumps({"style": style}),
                },
            )
    print(f"Seeded {len(FURNITURE_CATALOG)} furniture items.")


if __name__ == "__main__":
    seed()