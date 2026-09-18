# Databricks notebook source
# DBTITLE 1,Products
# MAGIC %md
# MAGIC # Products
# MAGIC Generate a synthetic beauty product catalog. Includes brands, categories, subcategories, pricing, organic flags, and customer ratings.

# COMMAND ----------

# DBTITLE 1,Load Configuration
import yaml
import os

notebook_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
project_dir = os.path.dirname(os.path.dirname(notebook_path))
config_path = f"/Workspace{project_dir}/config.yml"
with open(config_path, "r") as f:
    config = yaml.safe_load(f)

catalog = config["uc_catalog"]
schema = config["uc_schema"]
prefix = config["table_prefix"]
postfix = config["table_postfix"]
num_products = config["num_products"]

table_name = f"{catalog}.{schema}.{prefix}_products{postfix}"
print(f"Target: {table_name}")
print(f"Rows:   {num_products:,}")

# COMMAND ----------

# DBTITLE 1,Generate Product Catalog
import random
from pyspark.sql.types import *
from pyspark.sql import functions as F

random.seed(123)

# Beauty supply product taxonomy
category_products = {
    "Skincare": {
        "Cleanser": ["Foaming Gel Cleanser", "Micellar Water", "Oil Cleanser", "Cream Cleanser", "Exfoliating Wash"],
        "Moisturizer": ["Daily Hydrating Cream", "Gel Moisturizer", "Night Repair Cream", "Lightweight Lotion", "Rich Butter Cream"],
        "Serum": ["Vitamin C Serum", "Hyaluronic Acid Serum", "Retinol Serum", "Niacinamide Serum", "Peptide Complex"],
        "Sunscreen": ["SPF 50 Mineral Screen", "Tinted Sunscreen", "Lightweight UV Fluid", "Sport Sunscreen", "Daily Defense SPF 30"],
        "Toner": ["Balancing Toner", "Hydrating Essence", "Exfoliating Toner", "Rose Water Mist", "Witch Hazel Toner"],
        "Eye Cream": ["Anti-Wrinkle Eye Cream", "Brightening Eye Gel", "Firming Eye Balm", "Dark Circle Corrector"],
        "Face Mask": ["Clay Purifying Mask", "Sheet Mask Hydra", "Overnight Sleeping Mask", "Peel-Off Charcoal Mask"],
    },
    "Haircare": {
        "Shampoo": ["Volumizing Shampoo", "Color Protect Shampoo", "Moisturizing Shampoo", "Clarifying Shampoo", "Keratin Shampoo"],
        "Conditioner": ["Deep Repair Conditioner", "Leave-In Conditioner", "Lightweight Conditioner", "Color Safe Conditioner"],
        "Hair Oil": ["Argan Oil Treatment", "Coconut Hair Serum", "Frizz Control Oil", "Scalp Revitalizer Oil"],
        "Styling": ["Texturizing Spray", "Strong Hold Gel", "Curl Defining Cream", "Heat Protectant Spray", "Mousse Volume Boost"],
        "Hair Mask": ["Keratin Repair Mask", "Moisture Recovery Mask", "Bond Repair Treatment", "Protein Strengthener"],
    },
    "Makeup": {
        "Foundation": ["Liquid Matte Foundation", "Dewy Skin Tint", "Full Coverage Foundation", "BB Cream", "Powder Foundation"],
        "Concealer": ["Under-Eye Concealer", "Full Coverage Concealer", "Color Correcting Stick", "Brightening Concealer"],
        "Lipstick": ["Matte Lipstick", "Satin Lip Color", "Lip Gloss", "Lip Liner", "Tinted Lip Balm", "Liquid Lipstick"],
        "Mascara": ["Volumizing Mascara", "Lengthening Mascara", "Waterproof Mascara", "Tubing Mascara"],
        "Eyeshadow": ["12-Shade Palette", "Single Shadow", "Cream Shadow Stick", "Glitter Shadow", "Matte Quad Palette"],
        "Blush": ["Powder Blush", "Cream Blush", "Liquid Blush", "Blush Stick"],
        "Primer": ["Pore Minimizing Primer", "Illuminating Primer", "Mattifying Primer", "Hydrating Primer"],
    },
    "Nails": {
        "Nail Polish": ["Classic Lacquer", "Gel Effect Polish", "Quick Dry Polish", "Shimmer Polish", "Matte Top Coat"],
        "Nail Treatment": ["Nail Strengthener", "Cuticle Oil", "Ridge Filler", "Nail Growth Serum"],
        "Nail Art": ["Nail Sticker Set", "Stamping Kit", "Dotting Tool Set", "Nail Foils"],
        "Nail Remover": ["Acetone Remover", "Non-Acetone Remover", "Gel Remover Wraps"],
    },
    "Fragrance": {
        "Perfume": ["Eau de Parfum Floral", "Eau de Parfum Woody", "Eau de Toilette Fresh", "Signature Scent"],
        "Body Mist": ["Vanilla Bean Mist", "Citrus Burst Mist", "Ocean Breeze Mist", "Rose Garden Mist"],
        "Cologne": ["Classic Cologne", "Sport Cologne", "Evening Cologne"],
        "Rollerball": ["Travel Rollerball", "Pulse Point Oil", "Layering Rollerball Set"],
    },
    "Tools & Accessories": {
        "Brush Set": ["5-Piece Face Brush Set", "Eye Brush Duo", "Blending Sponge 3-Pack", "Kabuki Brush"],
        "Tools": ["Eyelash Curler", "Brow Razor 3-Pack", "Facial Roller Jade", "Dermaplaning Tool"],
        "Hair Tools": ["Ceramic Flat Iron", "Ionic Hair Dryer", "Curling Wand", "Detangling Brush", "Wide-Tooth Comb"],
        "Accessories": ["Makeup Bag", "LED Mirror", "Headband Set", "Reusable Cotton Pads"],
    },
}

brands = [
    "Fenty Beauty", "MAC", "NYX Professional", "Urban Decay", "Too Faced",
    "Maybelline", "L'Oréal", "Clinique", "Neutrogena", "CeraVe",
    "The Ordinary", "Olaplex", "Moroccanoil", "OPI", "Essie",
    "Revlon", "NARS", "Benefit", "Tatcha", "Drunk Elephant",
    "Glossier", "Rare Beauty", "Charlotte Tilbury", "IT Cosmetics",
    "e.l.f.", "ColourPop", "Tarte", "Anastasia Beverly Hills", "Bobbi Brown", "Kiehl's",
]

# Price ranges by category
price_ranges = {
    "Skincare": (8.99, 68.00),
    "Haircare": (7.99, 48.00),
    "Makeup": (5.99, 55.00),
    "Nails": (3.99, 24.00),
    "Fragrance": (12.99, 95.00),
    "Tools & Accessories": (4.99, 75.00),
}

# Build product rows by cycling through the taxonomy
rows = []
pid = 0
while pid < num_products:
    for category, subcats in category_products.items():
        for subcategory, products in subcats.items():
            for product_name in products:
                pid += 1
                if pid > num_products:
                    break
                low, high = price_ranges[category]
                price = round(random.uniform(low, high), 2)
                rows.append((
                    pid,
                    random.choice(brands),
                    product_name,
                    category,
                    subcategory,
                    price,
                    random.random() < 0.25,  # 25% organic
                    round(random.uniform(2.5, 5.0), 1),  # rating
                ))
            if pid > num_products:
                break
        if pid > num_products:
            break

df_products = spark.createDataFrame(rows, StructType([
    StructField("product_id", IntegerType()),
    StructField("brand", StringType()),
    StructField("product_name", StringType()),
    StructField("category", StringType()),
    StructField("subcategory", StringType()),
    StructField("unit_price", DoubleType()),
    StructField("is_organic", BooleanType()),
    StructField("rating", DoubleType()),
]))

print(f"Generated {df_products.count():,} products")
display(df_products.limit(10))

# COMMAND ----------

# DBTITLE 1,Write to Delta
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
df_products.write.format("delta").mode("overwrite").saveAsTable(table_name)
print(f"✓ Wrote {table_name}")

# COMMAND ----------

# DBTITLE 1,Apply Table and Column Descriptions
spark.sql(f"COMMENT ON TABLE {table_name} IS 'GlowMart product catalog including brand, category, pricing, and customer ratings.'")

col_comments = {
    "product_id": "Primary key. Unique product identifier.",
    "brand": "Brand name (e.g. Fenty Beauty, CeraVe, Olaplex).",
    "product_name": "Specific product name.",
    "category": "Top-level product category: Skincare, Haircare, Makeup, Nails, Fragrance, or Tools and Accessories.",
    "subcategory": "Product subcategory (e.g. Cleanser, Shampoo, Foundation, Nail Polish).",
    "unit_price": "Retail list price in USD. For the actual sale price at time of purchase, use the order_items table.",
    "is_organic": "Whether the product is organic (true/false).",
    "rating": "Average customer rating from 1.0 to 5.0.",
}
for col, desc in col_comments.items():
    spark.sql(f"ALTER TABLE {table_name} ALTER COLUMN {col} COMMENT '{desc}'")
print(f"✓ Applied descriptions to {table_name}")

# COMMAND ----------

# DBTITLE 1,Verify Distribution
display(spark.sql(f"""
    SELECT category, COUNT(*) as product_count,
           ROUND(AVG(unit_price), 2) as avg_price,
           ROUND(AVG(rating), 1) as avg_rating
    FROM {table_name}
    GROUP BY category
    ORDER BY product_count DESC
"""))