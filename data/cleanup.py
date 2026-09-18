# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Cleanup
# MAGIC %md
# MAGIC # Cleanup
# MAGIC Drop all workshop tables and optionally the schema. Run this after the workshop to clean up Unity Catalog resources.

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

print(f"Catalog: {catalog}")
print(f"Schema:  {schema}")
print(f"Prefix:  {prefix}")
print(f"Postfix: {postfix}")

# COMMAND ----------

# DBTITLE 1,Drop All Workshop Tables
tables = ["order_items", "inventory", "orders", "customers", "products", "stores"]

for t in tables:
    fqn = f"{catalog}.{schema}.{prefix}_{t}{postfix}"
    try:
        spark.sql(f"DROP TABLE IF EXISTS {fqn}")
        print(f"  ✓ Dropped {fqn}")
    except Exception as e:
        print(f"  ✗ Failed to drop {fqn}: {e}")

print(f"\n✓ All workshop tables removed.")

# COMMAND ----------

# DBTITLE 1,Drop Schema (Optional)
# Uncomment the line below to drop the schema entirely.
# Only do this if no other tables exist in the schema.

# spark.sql(f"DROP SCHEMA IF EXISTS {catalog}.{schema} CASCADE")
# print(f"✓ Dropped schema {catalog}.{schema}")