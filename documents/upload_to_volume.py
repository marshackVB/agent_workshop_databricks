# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Upload PDFs to Volume
# MAGIC %md
# MAGIC # Upload PDFs to Volume
# MAGIC Copy all `.pdf` files from the local documents directory to a Unity Catalog Volume. Creates the volume if it does not exist.

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
postfix = config["table_postfix"]
volume_name = f"{config['volume_name']}{postfix}"

volume_path = f"/Volumes/{catalog}/{schema}/{volume_name}"
print(f"Target volume: {volume_path}")

# COMMAND ----------

# DBTITLE 1,Create Volume If Not Exists
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.{schema}.{volume_name}")
print(f"✓ Volume ready: {catalog}.{schema}.{volume_name}")

# COMMAND ----------

# DBTITLE 1,Copy PDFs to Volume
import glob
import shutil

# PDF source: same directory as this notebook
docs_dir = f"/Workspace{os.path.dirname(notebook_path)}"
pdf_files = sorted(glob.glob(os.path.join(docs_dir, "*.pdf")))

print(f"Found {len(pdf_files)} PDF files in {docs_dir}\n")

for src in pdf_files:
    filename = os.path.basename(src)
    dst = os.path.join(volume_path, filename)
    shutil.copy2(src, dst)
    size = os.path.getsize(dst)
    print(f"  ✓ {filename} ({size:,} bytes)")

print(f"\n✓ Copied {len(pdf_files)} PDFs to {volume_path}")

# COMMAND ----------

# DBTITLE 1,Verify Volume Contents
files = dbutils.fs.ls(volume_path)
print(f"Files in {volume_path}:\n")
for f in files:
    print(f"  {f.name} ({f.size:,} bytes)")
print(f"\n✓ {len(files)} files in volume")