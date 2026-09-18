"""RAG specialist — chatbot node and tool router."""
from langchain_core.runnables.base import RunnableBinding
from langgraph.graph import END, MessagesState


system_message = """You are a trusted assistant capable of searching GlowMart workshop documentation. Based on the user's most recent question and relevent conversation history, call the documentation search tools you have access to. It's possible that only part of the user's question and recent conversation history is relevent to your area of expertise. Use your judgment to identify which parts of the user's question can be used to retrieve relevent documentation. Make sure your final answer is grounded on the documents returned by the tool."""


def config_chatbot(model_with_tools: RunnableBinding):
  """
  Configure the models and associated tools used by the RAG
  chatbot. This enables the same chatbot node implementation
  to be used in both supervisor and swarm architectures, even
  though the tool configuration is different between these
  architectures.
  """
  def chatbot(state: MessagesState):
    """
    Retrieve relevent documents based on the user's question and conversation
    history. Answer the user's question based on the documentation.
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
