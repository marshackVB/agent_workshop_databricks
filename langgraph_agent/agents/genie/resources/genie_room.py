"""GenieAgent resource — wraps the Genie Space as a LangGraph-compatible agent."""
from databricks_langchain.genie import GenieAgent
from databricks.sdk import WorkspaceClient
from langgraph_agent.config import GENIE_SPACE_ID

genie_agent = GenieAgent(
    genie_space_id=GENIE_SPACE_ID,
    genie_agent_name="GlowMart Data Analyst",
    description="Answers questions about GlowMart structured business data via text-to-SQL",
    client=WorkspaceClient(),
)
