"""LangGraph Supervisor — compiles the full supervisor graph.

Usage from a notebook:
    from langgraph_agent.supervisor import supervisor

    # Visualize
    display(Image(supervisor.get_graph().draw_mermaid_png()))

    # Invoke
    result = supervisor.invoke({"messages": [{"role": "user", "content": "What are the top 5 products?"}]})
    print(result["messages"][-1].content)
"""
from databricks_langchain import ChatDatabricks
from langgraph_supervisor import create_supervisor
from langgraph.prebuilt import ToolNode

from langgraph_agent.config import LLM_ENDPOINT

from langgraph_agent.agents.genie.graph import compile_genie_agent
from langgraph_agent.agents.genie.resources.model import model as genie_model
from langgraph_agent.agents.genie.tools import text_to_sql_tool

from langgraph_agent.agents.rag.graph import compile_rag_agent
from langgraph_agent.agents.rag.resources.model import model as rag_model
from langgraph_agent.agents.rag.tools import documentation_search_tool


# CONFIGURE SUB AGENTS
# Genie
genie_tools = [text_to_sql_tool]
genie_model_with_tools = genie_model.bind_tools(genie_tools, tool_choice="auto")
genie_tool_node = ToolNode(tools=genie_tools)

genie_agent = compile_genie_agent(genie_model_with_tools,
                                  genie_tool_node)
# RAG
rag_tools = [documentation_search_tool]
rag_model_with_tools = rag_model.bind_tools(rag_tools, tool_choice="auto")
rag_tool_node = ToolNode(tools=rag_tools)

rag_agent = compile_rag_agent(rag_model_with_tools,
                              rag_tool_node)


# CONFIGURE THE SUPERVISOR
supervisor_model = ChatDatabricks(endpoint=LLM_ENDPOINT)

system_prompt = """You are a supervisor tasked with calling the below agents to fullfill the user's request.

    - genie_agent: Performs text to SQL against GlowMart retail data tables and analyses results.
    - rag_agent: Retrieves GlowMart workshop documentation and answers questions related to these topics.

Assign work to one agent at a time, do not call agents in parallel. Do not do any work yourself.
"""

supervisor = create_supervisor(
    model=supervisor_model,
    agents=[rag_agent, genie_agent],
    prompt=system_prompt,
    add_handoff_back_messages=True,
    output_mode="last_message",
).compile()
