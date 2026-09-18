# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Parse and Chunk Documents
# MAGIC %md
# MAGIC # Parse and Chunk Documents
# MAGIC
# MAGIC Parse PDF documents from a Unity Catalog Volume using `ai_parse_document`, then split into semantic chunks using `ai_prep_search`. Persists two tables:
# MAGIC 1. **Parsed documents** — raw parse output.
# MAGIC 2. **Document chunks** — embedding-ready chunks for Vector Search

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
volume_name = f"{config['volume_name']}{postfix}"
parsed_table_name = config["parsed_documents_table_name"]
chunks_table_name = config["document_chunks_table_name"]

# Fully qualified table names
volume_path = f"/Volumes/{catalog}/{schema}/{volume_name}"
parsed_table = f"{catalog}.{schema}.{prefix}_{parsed_table_name}{postfix}"
chunks_table = f"{catalog}.{schema}.{prefix}_{chunks_table_name}{postfix}"

print(f"Volume:       {volume_path}")
print(f"Parsed table: {parsed_table}")
print(f"Chunks table: {chunks_table}")

# COMMAND ----------

# MAGIC %md #### Parse the documents into raw text and persist in a Dela Table
# MAGIC See the documentation for [ai_parse_document](https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_parse_document), which is one of Databrick's [AI Functions](https://docs.databricks.com/aws/en/large-language-models/ai-functions)

# COMMAND ----------

# DBTITLE 1,Parse Documents with ai_parse_document
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")

spark.sql(f"""
CREATE OR REPLACE TABLE {parsed_table} AS
SELECT
  _metadata.file_name AS file_name,
  content,
  ai_parse_document(content, MAP('version', '2.0')) AS parsed_content
FROM READ_FILES('{volume_path}/', format => 'binaryFile')
""")

row_count = spark.table(parsed_table).count()
print(f"\u2713 Parsed {row_count} documents \u2192 {parsed_table}")
display(spark.sql(f"""
  SELECT file_name, 
         parsed_content:metadata:schema_version AS schema_version,
         is_variant_null(parsed_content:error_status) AS parse_ok
  FROM {parsed_table}
"""))

# COMMAND ----------

# MAGIC %md View the parsed table. Parsed results are stored as a [VARIANT](https://docs.databricks.com/aws/en/sql/language-manual/data-types/variant-type) type.

# COMMAND ----------

display(spark.table(parsed_table))

# COMMAND ----------

# MAGIC %md #### Generate document chunks from the full document text
# MAGIC See the documentation for [ai_prep_search](https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_prep_search). These chunks can then be vectorized using an embedding model and used for semantic search.

# COMMAND ----------

# DBTITLE 1,Chunk Documents with ai_prep_search
spark.sql(f"""
CREATE OR REPLACE TABLE {chunks_table} AS
WITH prepped AS (
  SELECT
    file_name,
    ai_prep_search(parsed_content) AS result
  FROM {parsed_table}
  WHERE is_variant_null(parsed_content:error_status)
)
SELECT
  chunk.value:chunk_id::STRING AS chunk_id,
  chunk.value:chunk_position::INT AS chunk_position,
  chunk.value:chunk_to_retrieve::STRING AS chunk_to_retrieve,
  chunk.value:chunk_to_embed::STRING AS chunk_to_embed,
  prepped.file_name AS source_file
FROM prepped,
  LATERAL variant_explode(prepped.result:document:contents) AS chunk
""")

chunk_count = spark.table(chunks_table).count()
print(f"\u2713 Created {chunk_count} chunks \u2192 {chunks_table}")

# COMMAND ----------

# MAGIC %md View the document chunks table

# COMMAND ----------

display(spark.table(chunks_table))

# COMMAND ----------

# DBTITLE 1,Prepare Chunks Table for Vector Search
# Enable Change Data Feed (required for Delta Sync index)
spark.sql(f"ALTER TABLE {chunks_table} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")

# chunk_id must be NOT NULL for PK constraint
spark.sql(f"ALTER TABLE {chunks_table} ALTER COLUMN chunk_id SET NOT NULL")

# Add primary key constraint (required for Delta Sync index)
spark.sql(f"ALTER TABLE {chunks_table} DROP CONSTRAINT IF EXISTS pk_chunk_id")
spark.sql(f"ALTER TABLE {chunks_table} ADD CONSTRAINT pk_chunk_id PRIMARY KEY (chunk_id)")

print(f"\u2713 Change Data Feed enabled on {chunks_table}")
print(f"\u2713 PRIMARY KEY constraint added on chunk_id")

# COMMAND ----------

# DBTITLE 1,Verify Tables
print("=== Parsed Documents ===")
parsed_count = spark.table(parsed_table).count()
print(f"  {parsed_table}: {parsed_count} documents\n")

print("=== Document Chunks ===")
chunks_count = spark.table(chunks_table).count()
print(f"  {chunks_table}: {chunks_count} chunks\n")

print("=== Chunks per Source File ===")
display(spark.sql(f"""
  SELECT source_file, COUNT(*) AS chunk_count
  FROM {chunks_table}
  GROUP BY source_file
  ORDER BY source_file
"""))

print("\n=== Sample Chunk ===")
display(spark.sql(f"""
  SELECT chunk_id, chunk_position, source_file,
         LEFT(chunk_to_embed, 200) AS chunk_preview
  FROM {chunks_table}
  LIMIT 3
"""))