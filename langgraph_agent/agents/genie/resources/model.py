"""LLM for the Genie specialist agent."""
from databricks_langchain import ChatDatabricks
from langgraph_agent.config import LLM_ENDPOINT

model = ChatDatabricks(endpoint=LLM_ENDPOINT)
