# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Create Vector Search Index
# MAGIC %md
# MAGIC # Create Vector Search Index
# MAGIC
# MAGIC Provision a Vector Search endpoint and create a Delta Sync index on the document chunks table. The index uses managed embeddings — Databricks computes and stores the embedding vectors automatically.

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
chunks_table_name = config["document_chunks_table_name"]
vs_endpoint_name = config["vs_endpoint_name"]
embedding_model = config["embedding_model"]

# Derived names
chunks_table = f"{catalog}.{schema}.{prefix}_{chunks_table_name}{postfix}"
vs_index_name = config.get("vs_index_name", f"vs_index{postfix}")
index_name = f"{catalog}.{schema}.{vs_index_name}{postfix}"

print(f"Chunks table:  {chunks_table}")
print(f"VS endpoint:   {vs_endpoint_name}")
print(f"Index name:    {index_name}")
print(f"Embed model:   {embedding_model}")

# COMMAND ----------

# MAGIC %md #### Provision a Vector Search Endpoint if one does not already exist. 
# MAGIC VS Endpoints can serve multiple indexes so it is ok to re-use the endpoint.

# COMMAND ----------

# DBTITLE 1,Create Vector Search Endpoint
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.vectorsearch import EndpointType
from databricks.sdk.errors import NotFound
import time

w = WorkspaceClient()

# Create endpoint if it doesn't exist
try:
    ep = w.vector_search_endpoints.get_endpoint(vs_endpoint_name)
    print(f"Endpoint '{vs_endpoint_name}' already exists")
except NotFound:
    print(f"Creating endpoint '{vs_endpoint_name}'...")
    w.vector_search_endpoints.create_endpoint(
        name=vs_endpoint_name,
        endpoint_type=EndpointType.STANDARD
    )
    print("\u2713 Creation initiated")

# Wait for endpoint to be online
while True:
    ep = w.vector_search_endpoints.get_endpoint(vs_endpoint_name)
    state_str = str(ep.endpoint_status.state)
    if "ONLINE" in state_str.upper():
        print(f"\n\u2713 Endpoint '{vs_endpoint_name}' is ONLINE")
        break
    print(f"  Status: {state_str}... waiting 30s")
    time.sleep(30)

# COMMAND ----------

# MAGIC %md #### Verify that the document chunk table is ready to populate a Vector Search Index

# COMMAND ----------

# DBTITLE 1,Verify Chunks Table is Ready
# Confirm the chunks table exists and has the required properties
row_count = spark.table(chunks_table).count()
print(f"\u2713 {chunks_table}: {row_count} chunks")

# Confirm CDF is enabled
props = spark.sql(f"SHOW TBLPROPERTIES {chunks_table}").collect()
cdf_enabled = any(r["key"] == "delta.enableChangeDataFeed" and r["value"] == "true" for r in props)
print(f"\u2713 Change Data Feed: {'enabled' if cdf_enabled else 'NOT enabled \u2014 run 01_parse_and_chunk first!'}")

# Confirm PK exists
pk_check = spark.sql(f"""
  SELECT constraint_name FROM system.information_schema.table_constraints
  WHERE table_catalog = '{catalog}' AND table_schema = '{schema}'
    AND table_name = '{prefix}_{chunks_table_name}{postfix}'
    AND constraint_type = 'PRIMARY KEY'
""").collect()
pk_exists = len(pk_check) > 0
print(f"\u2713 Primary key: {'set (' + pk_check[0]['constraint_name'] + ')' if pk_exists else 'NOT set \u2014 run 01_parse_and_chunk first!'}")

# COMMAND ----------

# MAGIC %md #### Create a Delta Sync Index. 
# MAGIC
# MAGIC The Index will automatically detect changes to the source Delta table and embed the text chunks as part of the ingestion process.

# COMMAND ----------

# DBTITLE 1,Create Delta Sync Index
from databricks.sdk.service.vectorsearch import (
    DeltaSyncVectorIndexSpecRequest,
    EmbeddingSourceColumn,
    PipelineType,
    VectorIndexType,
)
from databricks.sdk.errors import NotFound, ResourceDoesNotExist

# Create the Delta Sync index with managed embeddings
try:
    existing_index = w.vector_search_indexes.get_index(index_name)
    print(f"Index '{index_name}' already exists")
    print(f"  Status: {existing_index.status}")
except (NotFound, ResourceDoesNotExist):
    print(f"Creating index '{index_name}'...")
    w.vector_search_indexes.create_index(
        name=index_name,
        endpoint_name=vs_endpoint_name,
        primary_key="chunk_id",
        index_type=VectorIndexType.DELTA_SYNC,
        delta_sync_index_spec=DeltaSyncVectorIndexSpecRequest(
            source_table=chunks_table,
            embedding_source_columns=[
                EmbeddingSourceColumn(
                    name="chunk_to_embed",
                    embedding_model_endpoint_name=embedding_model
                )
            ],
            pipeline_type=PipelineType.TRIGGERED,
            columns_to_sync=["chunk_id", "chunk_to_retrieve", "chunk_to_embed", "source_file"]
        )
    )
    print(f"\u2713 Index creation initiated")
    print(f"  Source: {chunks_table}")
    print(f"  Embedding column: chunk_to_embed")
    print(f"  Model: {embedding_model}")

# COMMAND ----------

# DBTITLE 1,Wait for Index to be Ready
import time

print(f"Waiting for index '{index_name}' to sync...\n")
while True:
    idx = w.vector_search_indexes.get_index(index_name)
    status = idx.status
    
    ready = getattr(status, 'ready', False)
    message = getattr(status, 'message', '')
    index_state = getattr(status, 'index_status', None)
    
    if ready:
        print(f"\n\u2713 Index '{index_name}' is ready!")
        break
    
    print(f"  Ready: {ready} | Status: {index_state} | {message[:80] if message else ''}")
    time.sleep(30)

# COMMAND ----------

# MAGIC %md #### Query the Vector Index

# COMMAND ----------

# DBTITLE 1,Test Query
# Run a sample similarity search
results = w.vector_search_indexes.query_index(
    index_name=index_name,
    columns=["chunk_id", "chunk_to_retrieve", "source_file"],
    query_text="What is the return policy?",
    num_results=3
)

print("Query: 'What is the return policy?'\n")
for i, row in enumerate(results.result.data_array):
    score = row[-1]
    chunk_text = row[1][:200] if row[1] else ""
    source = row[2]
    print(f"Result {i+1} (score: {score:.4f})")
    print(f"  Source: {source}")
    print(f"  Text:   {chunk_text}...\n")