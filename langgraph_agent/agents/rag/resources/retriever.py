"""Vector Search retriever resource."""
from databricks_langchain import DatabricksVectorSearch
from langgraph_agent.config import VS_ENDPOINT_NAME, VS_INDEX_NAME

# The VS index uses Databricks-managed embeddings and has a pre-configured
# source column, so neither embedding nor text_column should be passed.
retriever = DatabricksVectorSearch(
    endpoint=VS_ENDPOINT_NAME,
    index_name=VS_INDEX_NAME,
    columns=["chunk_id", "chunk_to_retrieve", "source_file"],
).as_retriever(search_kwargs={"k": 3, "query_type": "ann"})
