# Databricks notebook source
# DBTITLE 1,Install dependencies
# MAGIC %pip install "databricks-langchain>=0.20.0" "langgraph>=1.0.13" "langgraph-supervisor>=0.0.31" -q
# MAGIC %restart_python

# COMMAND ----------

# DBTITLE 1,Overview
# MAGIC %md
# MAGIC ## LangGraph Supervisor — Standalone Validation
# MAGIC
# MAGIC This notebook tests the LangGraph supervisor graph end-to-end **without the Databricks App serving shell**. Use it to:
# MAGIC
# MAGIC 1. Verify imports and dependency versions
# MAGIC 2. Compile the specialist agents and supervisor graph
# MAGIC 3. Test the RAG path (Vector Search)
# MAGIC 4. Test the Genie path (Genie Space API)
# MAGIC 5. Validate the MLflow response type construction
# MAGIC
# MAGIC Run this before deploying your app to catch issues early.

# COMMAND ----------

# DBTITLE 1,Build supervisor graph
from typing import Any
from databricks.sdk import WorkspaceClient
from databricks_langchain import ChatDatabricks
from langchain_core.tools import StructuredTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph_supervisor import create_supervisor
from pydantic import BaseModel, Field

print("✓ All imports succeeded")

# --- Load config from workshop config.yml ---
import yaml, pathlib
config_path = pathlib.Path(
    "/Workspace" + dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
).parent.parent / "config.yml"
with open(config_path) as f:
    config = yaml.safe_load(f)

GENIE_SPACE_ID = config.get("genie_agent_id", "")
VECTOR_SEARCH_INDEX = f"{config['uc_catalog']}.{config['uc_schema']}.{config.get('vs_index_name', 'vs_index')}{config['table_postfix']}"
AGENT_LLM_ENDPOINT = "databricks-gpt-5-2"
VECTOR_SEARCH_COLUMNS = ["chunk_id", "chunk_to_retrieve", "source_file"]
WORKSPACE_CLIENT = WorkspaceClient()

print(f"Genie Space ID: {GENIE_SPACE_ID}")
print(f"Vector Search index: {VECTOR_SEARCH_INDEX}")
print(f"LLM endpoint: {AGENT_LLM_ENDPOINT}")

# --- Tool schemas ---
class GenieQuestionSchema(BaseModel):
    question: str = Field(description="Question to send to the GlowMart Genie Space.")

class VectorSearchSchema(BaseModel):
    query: str = Field(description="Natural-language query for semantic document retrieval.")

# --- Tool implementations ---
def ask_genie(question: str) -> str:
    response = WORKSPACE_CLIENT.genie.start_conversation_and_wait(
        space_id=GENIE_SPACE_ID, content=question)
    parts = []
    for attachment in response.attachments or []:
        sql_text = getattr(getattr(attachment, "query", None), "query", None)
        answer_text = getattr(getattr(attachment, "text", None), "content", None)
        if sql_text: parts.append(f"SQL used by Genie:\n{sql_text}")
        if answer_text: parts.append(answer_text)
    return "\n\n".join(parts) if parts else "Genie returned no text response."

def search_documents(query: str) -> str:
    response = WORKSPACE_CLIENT.vector_search_indexes.query_index(
        index_name=VECTOR_SEARCH_INDEX, columns=VECTOR_SEARCH_COLUMNS,
        query_text=query, num_results=3)
    rows = response.result.data_array or []
    if not rows: return "No matching document chunks were found."
    results = []
    for i, row in enumerate(rows, start=1):
        chunk_id, chunk_text, source_file, score = row
        results.append(f"Result {i} | Source: {source_file} | Score: {score:.4f}\n{chunk_text[:200]}...")
    return "\n\n".join(results)

GENIE_TOOL = StructuredTool.from_function(ask_genie, name="ask_genie",
    description="Answer questions using the workshop Genie Space.",
    args_schema=GenieQuestionSchema, response_format="content", return_direct=True, verbose=False)

VECTOR_SEARCH_TOOL = StructuredTool.from_function(search_documents, name="search_documents",
    description="Search the workshop vector index for document chunks.",
    args_schema=VectorSearchSchema, response_format="content", return_direct=True, verbose=False)

print("✓ Tools created")

# --- System prompts ---
GENIE_PROMPT = "You are the Genie specialist for GlowMart data. Use the Genie tool to answer structured data questions."
RAG_PROMPT = "You are the document-search specialist. Use the vector search tool to find relevant document chunks."
SUPERVISOR_PROMPT = ("You are a supervisor coordinating two specialized agents.\n"
    "* genie: answers questions about GlowMart structured business data.\n"
    "* rag: answers questions from GlowMart workshop documents.\n"
    "Route work to one specialist at a time. Do not do the specialists' work yourself.")

# --- Graph construction ---
def build_model():
    return ChatDatabricks(endpoint=AGENT_LLM_ENDPOINT, extra_params={"temperature": 0})

def configure_chatbot(system_prompt, model_with_tools):
    def chatbot(state: MessagesState):
        messages = [{"role": "system", "content": system_prompt}] + state["messages"]
        return {"messages": [model_with_tools.invoke(messages)]}
    return chatbot

def route_tools(state: MessagesState):
    ai_message = state["messages"][-1]
    if hasattr(ai_message, "tool_calls") and len(ai_message.tool_calls) > 0:
        return "tools"
    return END

def compile_specialist_agent(name, system_prompt, tools):
    model_with_tools = build_model().bind_tools(tools, tool_choice="auto")
    tool_node = ToolNode(tools=tools)
    chatbot = configure_chatbot(system_prompt, model_with_tools)
    g = StateGraph(MessagesState)
    g.add_node("chatbot", chatbot)
    g.add_node("tools", tool_node)
    g.add_conditional_edges("chatbot", route_tools, {"tools": "tools", END: END})
    g.add_edge(START, "chatbot")
    g.add_edge("tools", "chatbot")
    return g.compile(name=name)

genie_agent = compile_specialist_agent("genie_agent", GENIE_PROMPT, [GENIE_TOOL])
rag_agent = compile_specialist_agent("rag_agent", RAG_PROMPT, [VECTOR_SEARCH_TOOL])
print("✓ Specialist agents compiled")

supervisor = create_supervisor(
    model=build_model(), agents=[rag_agent, genie_agent],
    prompt=SUPERVISOR_PROMPT, add_handoff_back_messages=True, output_mode="full_history",
).compile()
print("✓ Supervisor graph compiled")

# COMMAND ----------

# DBTITLE 1,Test 1: RAG path (Vector Search)
def extract_final_text(graph_result):
    """Walk backwards through graph output to find the last assistant text."""
    for message in reversed(graph_result.get("messages", [])):
        msg_type = getattr(message, "type", None)
        if msg_type not in {None, "ai"} and not isinstance(message, dict):
            continue
        content = getattr(message, "content", None) if not isinstance(message, dict) else message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    return "No final response."

result = supervisor.invoke({"messages": [{"role": "user", "content": "What is GlowMart's return policy?"}]})
final = extract_final_text(result)
print(f"=== RAG Test ===")
print(f"Response length: {len(final)} chars")
print(f"Response:\n{final[:500]}")

# COMMAND ----------

# DBTITLE 1,Test 2: Genie path (structured data)
result2 = supervisor.invoke({"messages": [{"role": "user", "content": "How many orders are there?"}]})
final2 = extract_final_text(result2)
print(f"=== Genie Test ===")
print(f"Response length: {len(final2)} chars")
print(f"Response:\n{final2[:500]}")

# COMMAND ----------

# DBTITLE 1,Test 3: Validate MLflow response types
import time
from uuid import uuid4
from mlflow.types.responses import ResponsesAgentResponse, ResponsesAgentStreamEvent
from mlflow.types.responses_helpers import (
    Content, OutputItem, Response,
    ResponseCompletedEvent, ResponseOutputItemDoneEvent, ResponseTextDeltaEvent,
)

# Build with the CORRECT types (OutputItem + Content, not ResponseOutputMessage + ResponseOutputText)
item_id = str(uuid4())
final_item = OutputItem(
    type="message", id=item_id, role="assistant", status="completed",
    content=[Content(type="output_text", text=final2, annotations=[])],
)

# Verify ResponsesAgentResponse accepts OutputItem
resp = ResponsesAgentResponse(
    id=str(uuid4()), created_at=time.time(), model=AGENT_LLM_ENDPOINT,
    status="completed", output=[final_item],
)
print(f"✓ ResponsesAgentResponse: id={resp.id}")

# Verify all 4 stream event types
initial_item = OutputItem(
    type="message", id=item_id, role="assistant", status="in_progress",
    content=[Content(type="output_text", text="", annotations=[])],
)
evt1 = ResponsesAgentStreamEvent(type="response.output_item.added", item=initial_item, output_index=0)
evt2 = ResponseTextDeltaEvent(content_index=0, delta="test", item_id=item_id, output_index=0)
evt3 = ResponseOutputItemDoneEvent(item=final_item, output_index=0)
evt4 = ResponseCompletedEvent(response=Response(
    id=str(uuid4()), created_at=time.time(), model=AGENT_LLM_ENDPOINT,
    status="completed", output=[final_item]))

print(f"✓ All 4 stream event types validated")
print(f"\n=== ALL VALIDATION CHECKS PASSED ===")