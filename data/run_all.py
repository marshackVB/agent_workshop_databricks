# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Run All Data Notebooks
# MAGIC %md
# MAGIC # Run All Data Notebooks
# MAGIC Executes all 6 data generation notebooks in dependency order. Phase 1 (independent) runs first, then Phase 2 (dependent).

# COMMAND ----------

# DBTITLE 1,Run All Notebooks
import os

notebook_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
base_path = os.path.dirname(notebook_path)
timeout = 600

phase1 = ["01_customers", "02_products", "03_stores", "04_orders"]
phase2 = ["05_order_items", "06_inventory"]

print("=== Phase 1 (independent tables) ===")
for nb in phase1:
    print(f"Running {nb}...")
    dbutils.notebook.run(f"{base_path}/{nb}", timeout)
    print(f"  ✓ {nb} complete")

print("\n=== Phase 2 (dependent tables) ===")
for nb in phase2:
    print(f"Running {nb}...")
    dbutils.notebook.run(f"{base_path}/{nb}", timeout)
    print(f"  ✓ {nb} complete")

print("\n✓ All 6 tables created successfully.")

# COMMAND ----------

# DBTITLE 1,Verify All Tables
import yaml
import os

config_path = f"/Workspace{os.path.dirname(base_path)}/config.yml"
with open(config_path, "r") as f:
    config = yaml.safe_load(f)

catalog = config["uc_catalog"]
schema = config["uc_schema"]
prefix = config["table_prefix"]
postfix = config["table_postfix"]

tables = ["customers", "products", "stores", "orders", "order_items", "inventory"]
for t in tables:
    fqn = f"{catalog}.{schema}.{prefix}_{t}{postfix}"
    count = spark.table(fqn).count()
    print(f"  {fqn}: {count:,} rows")

print(f"\n✓ All tables verified in {catalog}.{schema}")