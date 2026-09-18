# Databricks notebook source
# DBTITLE 1,Customers
# MAGIC %md
# MAGIC # Customers
# MAGIC Generate synthetic customer profiles for a beauty supply retailer. Includes demographics, loyalty tiers, shopping channel preferences, and skin type data.

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
num_customers = config["num_customers"]

table_name = f"{catalog}.{schema}.{prefix}_customers{postfix}"
print(f"Target: {table_name}")
print(f"Rows:   {num_customers:,}")

# COMMAND ----------

# DBTITLE 1,Generate Customer Data
import random
from datetime import date, timedelta
from pyspark.sql.types import *
from pyspark.sql import functions as F

random.seed(42)

first_names = [
    "Emma", "Olivia", "Ava", "Isabella", "Sophia", "Mia", "Charlotte", "Amelia",
    "Harper", "Evelyn", "Abigail", "Emily", "Elizabeth", "Sofia", "Ella", "Madison",
    "Scarlett", "Victoria", "Aria", "Grace", "Chloe", "Camila", "Penelope", "Riley",
    "James", "Robert", "John", "Michael", "David", "William", "Richard", "Joseph",
    "Thomas", "Christopher", "Charles", "Daniel", "Matthew", "Anthony", "Mark", "Steven",
    "Andrew", "Paul", "Joshua", "Kenneth", "Kevin", "Brian", "George", "Timothy",
]

last_names = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson",
]

loyalty_tiers = ["Bronze", "Silver", "Gold", "Platinum"]
loyalty_weights = [0.40, 0.30, 0.20, 0.10]
channels = ["online", "in-store"]
skin_types = ["oily", "dry", "combination", "normal", "sensitive"]

states_cities = {
    "TX": ["Houston", "Dallas", "Austin", "San Antonio", "Fort Worth", "El Paso"],
    "CA": ["Los Angeles", "San Francisco", "San Diego", "Sacramento", "San Jose"],
    "NY": ["New York", "Brooklyn", "Queens", "Buffalo", "Rochester"],
    "FL": ["Miami", "Orlando", "Tampa", "Jacksonville", "Fort Lauderdale"],
    "IL": ["Chicago", "Aurora", "Naperville", "Joliet", "Springfield"],
    "GA": ["Atlanta", "Savannah", "Augusta", "Columbus", "Macon"],
    "NC": ["Charlotte", "Raleigh", "Durham", "Greensboro", "Wilmington"],
    "PA": ["Philadelphia", "Pittsburgh", "Allentown", "Erie", "Reading"],
    "AZ": ["Phoenix", "Tucson", "Mesa", "Scottsdale", "Chandler"],
    "OH": ["Columbus", "Cleveland", "Cincinnati", "Toledo", "Akron"],
}

start_date = date(2019, 1, 1)
date_range = (date(2024, 12, 31) - start_date).days

rows = []
for i in range(1, num_customers + 1):
    state = random.choice(list(states_cities.keys()))
    city = random.choice(states_cities[state])
    first = random.choice(first_names)
    last = random.choice(last_names)
    signup = start_date + timedelta(days=random.randint(0, date_range))

    rows.append((
        i, first, last,
        f"{first.lower()}.{last.lower()}{i}@email.com",
        random.choices(loyalty_tiers, weights=loyalty_weights, k=1)[0],
        random.choice(channels),
        random.choice(skin_types),
        city, state, signup.isoformat(),
    ))

df_customers = spark.createDataFrame(rows, StructType([
    StructField("customer_id", IntegerType()),
    StructField("first_name", StringType()),
    StructField("last_name", StringType()),
    StructField("email", StringType()),
    StructField("loyalty_tier", StringType()),
    StructField("preferred_channel", StringType()),
    StructField("skin_type", StringType()),
    StructField("city", StringType()),
    StructField("state", StringType()),
    StructField("signup_date", StringType()),
]))

df_customers = df_customers.withColumn("signup_date", F.col("signup_date").cast("date"))
print(f"Generated {df_customers.count():,} customers")
display(df_customers.limit(10))

# COMMAND ----------

# DBTITLE 1,Write to Delta
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
df_customers.write.format("delta").mode("overwrite").saveAsTable(table_name)
print(f"✓ Wrote {table_name}")

# COMMAND ----------

# DBTITLE 1,Apply Table and Column Descriptions
spark.sql(f"COMMENT ON TABLE {table_name} IS 'GlowMart customer profiles including loyalty tier, preferred shopping channel, skin type, and location.'")

col_comments = {
    "customer_id": "Primary key. Unique customer identifier.",
    "first_name": "Customer first name.",
    "last_name": "Customer last name.",
    "email": "Unique customer email address.",
    "loyalty_tier": "Customer loyalty tier: Bronze, Silver, Gold, or Platinum (Platinum is most valuable).",
    "preferred_channel": "Customer preferred shopping channel: online or in-store.",
    "skin_type": "Customer skin type: oily, dry, combination, normal, or sensitive.",
    "city": "Customer city of residence. Not the same as store city.",
    "state": "Customer state of residence (2-letter code). Not the same as store state.",
    "signup_date": "Date the customer joined GlowMart.",
}
for col, desc in col_comments.items():
    spark.sql(f"ALTER TABLE {table_name} ALTER COLUMN {col} COMMENT '{desc}'")
print(f"✓ Applied descriptions to {table_name}")

# COMMAND ----------

# DBTITLE 1,Verify Distribution
display(spark.sql(f"""
    SELECT loyalty_tier, preferred_channel, COUNT(*) as customer_count
    FROM {table_name}
    GROUP BY loyalty_tier, preferred_channel
    ORDER BY loyalty_tier, preferred_channel
"""))