"""Genie specialist — chatbot node and tool router."""
from langchain_core.runnables.base import RunnableBinding
from langgraph.graph import END, MessagesState


system_message = """You are a trusted assistant capable of interacting with GlowMart retail data using a text to sql tool. Based on the user's most recent question and relevent conversation history, create a question to pass to the text to sql tool. Analyze the data returned to answer the user's question. Make sure your final answer is grounded in the data. Do not answer questions related to other topics."""


def config_chatbot(model_with_tools: RunnableBinding):
  """
  Configure the models and associated tools used by the Genie
  chatbot. This enables the same chatbot node implementation
  to be used in both supervisor and swarm architectures, even
  though the tool configuration is different between these
  architectures.
  """
  def chatbot(state: MessagesState):
    """
    Send the user's question to the text-to-SQL tool and
    return the data results.
    """
    messages = [{"role": "system", "content": system_message}] + state["messages"]
    response = model_with_tools.invoke(messages)
    return {"messages": [response]}
  return chatbot


def route_tools(state: MessagesState):
  """
  A router that determines if tools should be called or a final
  answer returned to the user.
  """
  ai_message = state["messages"][-1]

  if hasattr(ai_message, "tool_calls") and len(ai_message.tool_calls) > 0:
        return "tools"

  return END
