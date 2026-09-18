# Databricks notebook source
# DBTITLE 1,Inventory
# MAGIC %md
# MAGIC # Inventory
# MAGIC Generate stock levels for stores. Not every product is stocked in every store — Express stores carry fewer SKUs than Flagships. Includes reorder points and restock dates.

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

table_name = f"{catalog}.{schema}.{prefix}_inventory{postfix}"
stores_table = f"{catalog}.{schema}.{prefix}_stores{postfix}"
products_table = f"{catalog}.{schema}.{prefix}_products{postfix}"

print(f"Target:   {table_name}")
print(f"Reading:  {stores_table}")
print(f"Reading:  {products_table}")

# COMMAND ----------

# DBTITLE 1,Generate Inventory Data
from pyspark.sql import functions as F
from pyspark.sql.types import *

df_stores = spark.table(stores_table).select("store_id", "store_type")
df_products = spark.table(products_table).select("product_id")
num_products = df_products.count()

# Cross join all stores × products
df_cross = df_stores.crossJoin(df_products)

# Stocking probability varies by store type:
#   Flagship: 90% of products   Standard: 70%   Express: 40%
df_cross = df_cross.withColumn(
    "_stock_prob",
    F.when(F.col("store_type") == "Flagship", 0.90)
     .when(F.col("store_type") == "Standard", 0.70)
     .otherwise(0.40)
)

# Filter to only stocked items
df_inventory = df_cross.filter(F.rand(seed=60) < F.col("_stock_prob"))

# Quantity on hand: higher for flagship, lower for express
df_inventory = df_inventory.withColumn(
    "quantity_on_hand",
    F.when(F.col("store_type") == "Flagship", (F.floor(F.rand(seed=61) * 150) + 10).cast("int"))
     .when(F.col("store_type") == "Standard", (F.floor(F.rand(seed=62) * 100) + 5).cast("int"))
     .otherwise((F.floor(F.rand(seed=63) * 40) + 2).cast("int"))
)

# Reorder point: typically 10-25% of max stock
df_inventory = df_inventory.withColumn(
    "reorder_point", (F.floor(F.col("quantity_on_hand") * (F.rand(seed=64) * 0.15 + 0.10))).cast("int")
)

# Last restocked: random date in the last 90 days
df_inventory = df_inventory.withColumn(
    "last_restocked_date",
    F.date_sub(F.current_date(), (F.floor(F.rand(seed=65) * 90)).cast("int"))
)

# Flag items below reorder point
df_inventory = df_inventory.withColumn(
    "needs_reorder",
    F.col("quantity_on_hand") <= F.col("reorder_point")
)

# Select final columns
df_inventory = df_inventory.select(
    "store_id", "product_id", "quantity_on_hand",
    "reorder_point", "last_restocked_date", "needs_reorder"
)

print(f"Generated {df_inventory.count():,} inventory records")
print(f"Items needing reorder: {df_inventory.filter(F.col('needs_reorder')).count():,}")
display(df_inventory.limit(10))

# COMMAND ----------

# DBTITLE 1,Write to Delta
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
df_inventory.write.format("delta").mode("overwrite").saveAsTable(table_name)
print(f"✓ Wrote {table_name}")

# COMMAND ----------

# DBTITLE 1,Apply Table and Column Descriptions
spark.sql(f"COMMENT ON TABLE {table_name} IS 'Current stock levels for each product at each physical store. Does not cover online warehouse stock.'")

col_comments = {
    "store_id": "Foreign key to stores table. Part of composite primary key with product_id.",
    "product_id": "Foreign key to products table. Part of composite primary key with store_id.",
    "quantity_on_hand": "Current stock level.",
    "reorder_point": "Stock threshold that triggers a reorder.",
    "last_restocked_date": "Date of most recent restock.",
    "needs_reorder": "True if quantity_on_hand is at or below reorder_point.",
}
for col, desc in col_comments.items():
    spark.sql(f"ALTER TABLE {table_name} ALTER COLUMN {col} COMMENT '{desc}'")
print(f"✓ Applied descriptions to {table_name}")

# COMMAND ----------

# DBTITLE 1,Verify Distribution
display(spark.sql(f"""
    SELECT s.store_type,
           COUNT(*) as sku_count,
           ROUND(AVG(i.quantity_on_hand)) as avg_qty,
           SUM(CASE WHEN i.needs_reorder THEN 1 ELSE 0 END) as needs_reorder_count
    FROM {table_name} i
    JOIN {stores_table} s ON i.store_id = s.store_id
    GROUP BY s.store_type
    ORDER BY sku_count DESC
"""))