"""RAG tool — wraps the Vector Search retriever as a LangChain StructuredTool."""
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from langgraph_agent.agents.rag.resources.retriever import retriever


def search_documentation(search: str):

  search_results = retriever.invoke(search)

  return search_results


class SearchSchema(BaseModel):
    search: str = Field(description="Text to search. A similarity search will retrieve documentation most similar to the search terms.")


documentation_search_tool = StructuredTool.from_function(search_documentation,
                                               name="search_documentation",
                                               description="Search the GlowMart workshop documentation to retrieve relevent information",
                                               args_schema=SearchSchema,
                                               response_format="content",
                                               return_direct=True,
                                               verbose=False)
