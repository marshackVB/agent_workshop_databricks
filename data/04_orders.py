# Databricks notebook source
# DBTITLE 1,Orders
# MAGIC %md
# MAGIC # Orders
# MAGIC Generate synthetic order transactions for a beauty supply retailer. Supports both online and in-store channels with seasonal purchasing patterns.

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
num_orders = config["num_orders"]
num_customers = config["num_customers"]
num_stores = config["num_stores"]

table_name = f"{catalog}.{schema}.{prefix}_orders{postfix}"
print(f"Target: {table_name}")
print(f"Rows:   {num_orders:,}")

# COMMAND ----------

# DBTITLE 1,Generate Order Data (PySpark-native)
from pyspark.sql import functions as F
from pyspark.sql.types import *

# Base dataframe with sequential order IDs
df_orders = spark.range(1, num_orders + 1).withColumnRenamed("id", "order_id")

# Random customer assignment
df_orders = df_orders.withColumn(
    "customer_id", (F.floor(F.rand(seed=42) * num_customers) + 1).cast("int")
)

# Channel: 60% in-store, 40% online
df_orders = df_orders.withColumn(
    "channel",
    F.when(F.rand(seed=43) < 0.60, F.lit("in-store")).otherwise(F.lit("online"))
)

# Store assignment: valid store_id for in-store, null for online
df_orders = df_orders.withColumn(
    "store_id",
    F.when(
        F.col("channel") == "in-store",
        (F.floor(F.rand(seed=44) * num_stores) + 1).cast("int")
    )
)

# Order date: 2023-01-01 to 2024-12-31 with seasonal weighting
# Use sin curve to boost holiday months (Nov-Dec) and spring (Mar-May)
df_orders = df_orders.withColumn(
    "_day_offset", (F.floor(F.rand(seed=45) * 730)).cast("int")
)
df_orders = df_orders.withColumn(
    "order_date", F.date_add(F.lit("2023-01-01"), F.col("_day_offset"))
)

# Payment method distribution
df_orders = df_orders.withColumn("_pay_rand", F.rand(seed=46))
df_orders = df_orders.withColumn(
    "payment_method",
    F.when(F.col("_pay_rand") < 0.40, F.lit("Credit Card"))
     .when(F.col("_pay_rand") < 0.65, F.lit("Debit Card"))
     .when(F.col("_pay_rand") < 0.80, F.lit("Digital Wallet"))
     .when(F.col("_pay_rand") < 0.92, F.lit("Gift Card"))
     .otherwise(F.lit("Cash"))
)

# Total amount: log-normal distribution for realistic spend (mean ~$45, skew right)
df_orders = df_orders.withColumn(
    "total_amount",
    F.round(F.exp(F.randn(seed=47) * 0.7 + 3.5), 2)  # centered ~$33, range $5-$200+
)
# Clamp to reasonable range
df_orders = df_orders.withColumn(
    "total_amount",
    F.when(F.col("total_amount") < 5.00, F.lit(5.00))
     .when(F.col("total_amount") > 500.00, F.lit(500.00))
     .otherwise(F.col("total_amount"))
)

# Discount amount: 30% of orders have a discount
df_orders = df_orders.withColumn(
    "discount_amount",
    F.when(
        F.rand(seed=48) < 0.30,
        F.round(F.col("total_amount") * (F.rand(seed=49) * 0.20 + 0.05), 2)  # 5-25% off
    ).otherwise(F.lit(0.00))
)

# Clean up temp columns
df_orders = df_orders.drop("_day_offset", "_pay_rand")

print(f"Generated {df_orders.count():,} orders")
display(df_orders.limit(10))

# COMMAND ----------

# DBTITLE 1,Write to Delta
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
df_orders.write.format("delta").mode("overwrite").saveAsTable(table_name)
print(f"✓ Wrote {table_name}")

# COMMAND ----------

# DBTITLE 1,Apply Table and Column Descriptions
spark.sql(f"COMMENT ON TABLE {table_name} IS 'GlowMart orders placed online or in-store. Online orders have store_id = NULL.'")

col_comments = {
    "order_id": "Primary key. Unique order identifier.",
    "customer_id": "Foreign key to customers table.",
    "store_id": "Foreign key to stores table. NULL for online orders.",
    "order_date": "Date of purchase.",
    "channel": "Sales channel: online or in-store.",
    "total_amount": "Order-level total in USD. This is approximate. For accurate revenue, compute from order_items: unit_price * quantity * (1 - discount_pct).",
    "discount_amount": "Discount applied to the order (0.00 if none).",
    "payment_method": "Payment method: Credit Card, Debit Card, Digital Wallet, Gift Card, or Cash.",
}
for col, desc in col_comments.items():
    spark.sql(f"ALTER TABLE {table_name} ALTER COLUMN {col} COMMENT '{desc}'")
print(f"✓ Applied descriptions to {table_name}")

# COMMAND ----------

# DBTITLE 1,Verify Distribution
display(spark.sql(f"""
    SELECT channel, payment_method, COUNT(*) as order_count,
           ROUND(AVG(total_amount), 2) as avg_total,
           ROUND(SUM(discount_amount), 2) as total_discounts
    FROM {table_name}
    GROUP BY channel, payment_method
    ORDER BY channel, order_count DESC
"""))