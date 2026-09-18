"""Compile the Genie specialist sub-graph."""
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode
from langchain_core.runnables.base import RunnableBinding
from langgraph_agent.agents.genie.nodes import config_chatbot, route_tools


def compile_genie_agent(model_with_tools: RunnableBinding, tool_node: ToolNode):
  """
  Build the Genie agent with flexibility to pass different
  models and associated tools.
  """
  chatbot = config_chatbot(model_with_tools)

  graph_builder = StateGraph(MessagesState)
  graph_builder.add_node("chatbot", chatbot)
  graph_builder.add_node("tools", tool_node)
  graph_builder.add_conditional_edges("chatbot", route_tools,
      {"tools": "tools",
        END: END}
    )
  graph_builder.add_edge(START, "chatbot")
  graph_builder.add_edge("tools", "chatbot")
  return graph_builder.compile(name="genie_agent")
