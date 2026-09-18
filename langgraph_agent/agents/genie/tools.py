"""Genie tool — wraps GenieAgent.invoke() as a LangChain StructuredTool."""
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from langgraph_agent.agents.genie.resources.genie_room import genie_agent


def text_to_sql(question: str):
  """A question that will be used by an agent to
  generate a SQL query. The query will be executed and data
  results returned."""

  message = {"messages": [{"role": "user", "content": question}]}
  result = genie_agent.invoke(message)
  table = result['messages'][0].content
  return table


class SQLSchema(BaseModel):
    question: str = Field(description="A question that will be translated into a SQL query.")


text_to_sql_tool = StructuredTool.from_function(text_to_sql,
                                               name="text_to_sql",
                                               description="Convert a question to a SQL query and return the resulting data",
                                               args_schema=SQLSchema,
                                               response_format="content",
                                               return_direct=True,
                                               verbose=False)
