# Databricks notebook source
# DBTITLE 1,Stores
# MAGIC %md
# MAGIC # Stores
# MAGIC Generate synthetic store locations for a beauty supply retailer with flagship, standard, and express formats across multiple states.

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
num_stores = config["num_stores"]

table_name = f"{catalog}.{schema}.{prefix}_stores{postfix}"
print(f"Target: {table_name}")
print(f"Rows:   {num_stores:,}")

# COMMAND ----------

# DBTITLE 1,Generate Store Data
import random
from datetime import date, timedelta
from pyspark.sql.types import *
from pyspark.sql import functions as F

random.seed(99)

store_types = ["Flagship", "Standard", "Express"]
store_type_weights = [0.10, 0.60, 0.30]

# Square footage ranges by store type
sqft_ranges = {
    "Flagship": (8000, 15000),
    "Standard": (3000, 7000),
    "Express": (800, 2500),
}

# Realistic store locations spread across states
locations = [
    ("Houston", "TX", "77001"), ("Dallas", "TX", "75201"), ("Austin", "TX", "78701"),
    ("San Antonio", "TX", "78201"), ("Fort Worth", "TX", "76101"), ("El Paso", "TX", "79901"),
    ("Plano", "TX", "75023"), ("Arlington", "TX", "76010"),
    ("Los Angeles", "CA", "90001"), ("San Francisco", "CA", "94102"),
    ("San Diego", "CA", "92101"), ("Sacramento", "CA", "95814"), ("San Jose", "CA", "95112"),
    ("New York", "NY", "10001"), ("Brooklyn", "NY", "11201"), ("Queens", "NY", "11101"),
    ("Miami", "FL", "33101"), ("Orlando", "FL", "32801"), ("Tampa", "FL", "33601"),
    ("Jacksonville", "FL", "32099"),
    ("Chicago", "IL", "60601"), ("Naperville", "IL", "60540"),
    ("Atlanta", "GA", "30301"), ("Savannah", "GA", "31401"),
    ("Charlotte", "NC", "28201"), ("Raleigh", "NC", "27601"),
    ("Philadelphia", "PA", "19101"), ("Pittsburgh", "PA", "15201"),
    ("Phoenix", "AZ", "85001"), ("Scottsdale", "AZ", "85250"),
    ("Columbus", "OH", "43085"), ("Cleveland", "OH", "44101"),
    ("Denver", "CO", "80201"), ("Boulder", "CO", "80301"),
    ("Seattle", "WA", "98101"), ("Portland", "OR", "97201"),
    ("Nashville", "TN", "37201"), ("Memphis", "TN", "38101"),
    ("Las Vegas", "NV", "89101"), ("Minneapolis", "MN", "55401"),
    ("Detroit", "MI", "48201"), ("Boston", "MA", "02101"),
    ("Baltimore", "MD", "21201"), ("Washington", "DC", "20001"),
    ("New Orleans", "LA", "70112"), ("Kansas City", "MO", "64101"),
    ("Salt Lake City", "UT", "84101"), ("Indianapolis", "IN", "46201"),
    ("Richmond", "VA", "23218"), ("Milwaukee", "WI", "53201"),
]

start_date = date(2010, 1, 1)
date_range = (date(2024, 6, 30) - start_date).days

manager_first = ["Sarah", "Jessica", "Ashley", "Amanda", "Nicole", "Maria", "Lisa", "Angela", "Diana", "Rachel"]
manager_last = ["Chen", "Patel", "Kim", "Reyes", "Foster", "Brooks", "Rivera", "Hayes", "Bell", "Murphy"]

rows = []
for i in range(1, num_stores + 1):
    city, state, zipcode = locations[(i - 1) % len(locations)]
    stype = random.choices(store_types, weights=store_type_weights, k=1)[0]
    low, high = sqft_ranges[stype]
    sqft = random.randint(low, high)
    opened = start_date + timedelta(days=random.randint(0, date_range))
    manager = f"{random.choice(manager_first)} {random.choice(manager_last)}"

    rows.append((
        i,
        f"GlowMart {city}",
        city, state, zipcode,
        sqft, stype,
        opened.isoformat(),
        manager,
    ))

df_stores = spark.createDataFrame(rows, StructType([
    StructField("store_id", IntegerType()),
    StructField("store_name", StringType()),
    StructField("city", StringType()),
    StructField("state", StringType()),
    StructField("zip_code", StringType()),
    StructField("square_footage", IntegerType()),
    StructField("store_type", StringType()),
    StructField("opening_date", StringType()),
    StructField("manager_name", StringType()),
]))

df_stores = df_stores.withColumn("opening_date", F.col("opening_date").cast("date"))
print(f"Generated {df_stores.count():,} stores")
display(df_stores.limit(10))

# COMMAND ----------

# DBTITLE 1,Write to Delta
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
df_stores.write.format("delta").mode("overwrite").saveAsTable(table_name)
print(f"✓ Wrote {table_name}")

# COMMAND ----------

# DBTITLE 1,Apply Table and Column Descriptions
spark.sql(f"COMMENT ON TABLE {table_name} IS 'GlowMart physical store locations with type (Flagship, Standard, Express) and manager.'")

col_comments = {
    "store_id": "Primary key. Unique store identifier.",
    "store_name": "Store display name in the format GlowMart City.",
    "city": "Store city. Not the same as customer city.",
    "state": "Store state (2-letter code). Not the same as customer state.",
    "zip_code": "Store ZIP code.",
    "square_footage": "Store size in square feet.",
    "store_type": "Store format: Flagship (large, full assortment), Standard (mid-size), or Express (small, approximately 40% of catalog).",
    "opening_date": "Date the store opened.",
    "manager_name": "Current store manager.",
}
for col, desc in col_comments.items():
    spark.sql(f"ALTER TABLE {table_name} ALTER COLUMN {col} COMMENT '{desc}'")
print(f"✓ Applied descriptions to {table_name}")

# COMMAND ----------

# DBTITLE 1,Verify Distribution
display(spark.sql(f"""
    SELECT store_type, state, COUNT(*) as store_count,
           ROUND(AVG(square_footage)) as avg_sqft
    FROM {table_name}
    GROUP BY store_type, state
    ORDER BY store_type, store_count DESC
"""))