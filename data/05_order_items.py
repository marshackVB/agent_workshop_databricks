# Databricks notebook source
# DBTITLE 1,Order Items
# MAGIC %md
# MAGIC # Order Items
# MAGIC Generate line-item details for each order. Each order gets 1–6 items (avg 3–4) with product references, quantities, and per-item discounts. Depends on orders and products tables.

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

table_name = f"{catalog}.{schema}.{prefix}_order_items{postfix}"
orders_table = f"{catalog}.{schema}.{prefix}_orders{postfix}"
products_table = f"{catalog}.{schema}.{prefix}_products{postfix}"

print(f"Target:   {table_name}")
print(f"Reading:  {orders_table}")
print(f"Reading:  {products_table}")

# COMMAND ----------

# DBTITLE 1,Generate Order Items
from pyspark.sql import functions as F
from pyspark.sql.types import *

# Get product prices for realistic unit_price assignment
df_products = spark.table(products_table).select("product_id", "unit_price")
df_orders = spark.table(orders_table).select("order_id")

# Explode each order into 1-6 line items using a random item count
df_orders_with_count = df_orders.withColumn(
    "num_items", (F.floor(F.rand(seed=50) * 6) + 1).cast("int")  # 1 to 6 items
)

# Generate item indices using explode + sequence
df_exploded = df_orders_with_count.withColumn(
    "item_seq", F.explode(F.sequence(F.lit(1), F.col("num_items")))
)

# Assign random product_id per line item
df_items = df_exploded.withColumn(
    "product_id", (F.floor(F.rand(seed=51) * num_products) + 1).cast("int")
)

# Quantity: mostly 1-2, occasionally up to 5
df_items = df_items.withColumn(
    "quantity",
    F.when(F.rand(seed=52) < 0.60, F.lit(1))
     .when(F.rand(seed=53) < 0.80, F.lit(2))
     .when(F.rand(seed=54) < 0.90, F.lit(3))
     .otherwise((F.floor(F.rand(seed=55) * 3) + 3).cast("int"))  # 3-5
)

# Join to get the product's unit_price
df_items = df_items.join(df_products, "product_id", "left")

# Per-item discount: 20% of items get 5-30% off
df_items = df_items.withColumn(
    "discount_pct",
    F.when(
        F.rand(seed=56) < 0.20,
        F.round(F.rand(seed=57) * 0.25 + 0.05, 2)  # 5-30%
    ).otherwise(F.lit(0.00))
)

# Add monotonically increasing ID
df_items = df_items.withColumn("order_item_id", F.monotonically_increasing_id() + 1)

# Select final columns
df_order_items = df_items.select(
    "order_item_id", "order_id", "product_id",
    "quantity", "unit_price", "discount_pct"
)

print(f"Generated {df_order_items.count():,} order items")
print(f"Avg items per order: {df_order_items.count() / df_orders.count():.1f}")
display(df_order_items.limit(10))

# COMMAND ----------

# DBTITLE 1,Write to Delta
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
df_order_items.write.format("delta").mode("overwrite").saveAsTable(table_name)
print(f"✓ Wrote {table_name}")

# COMMAND ----------

# DBTITLE 1,Apply Table and Column Descriptions
spark.sql(f"COMMENT ON TABLE {table_name} IS 'Individual line items within each order, with per-item pricing and discount.'")

col_comments = {
    "order_item_id": "Primary key. Unique line item identifier.",
    "order_id": "Foreign key to orders table.",
    "product_id": "Foreign key to products table.",
    "quantity": "Number of units purchased (1-5).",
    "unit_price": "Price per unit at time of sale (may differ from catalog price).",
    "discount_pct": "Per-item discount as a decimal (0.00 to 0.30, where 0.10 = 10% off).",
}
for col, desc in col_comments.items():
    spark.sql(f"ALTER TABLE {table_name} ALTER COLUMN {col} COMMENT '{desc}'")
print(f"✓ Applied descriptions to {table_name}")

# COMMAND ----------

# DBTITLE 1,Verify Distribution
display(spark.sql(f"""
    SELECT p.category,
           COUNT(*) as items_sold,
           ROUND(AVG(oi.unit_price), 2) as avg_unit_price,
           ROUND(AVG(oi.discount_pct) * 100, 1) as avg_discount_pct
    FROM {table_name} oi
    JOIN {products_table} p ON oi.product_id = p.product_id
    GROUP BY p.category
    ORDER BY items_sold DESC
"""))