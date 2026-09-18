"""MCP-Based Agent — Reference Implementation

This is the working agent.py that enhances the default OpenAI Agents SDK
"deploy your own agent" template with Databricks managed MCP servers for
Genie Agent (structured data) and AI Search (document retrieval).

Key changes from the default template:
  1. Added init_genie_mcp_server() and init_ai_search_mcp_server()
  2. Wired all 3 MCP servers into both invoke and stream handlers
  3. Updated agent name to "GlowMart Assistant" and instructions with
     routing guidance for each MCP tool
  4. Used short VS index name (vs_index{postfix}) to stay under the
     64-character MCP tool name limit

Serving shell (unchanged from template):
  - start_server.py  — mlflow.genai.agent_server.AgentServer
  - history.py       — normalize_history_items()
  - utils.py         — get_session_id(), get_user_workspace_client(),
                       build_mcp_url()

Known gotchas:
  1. MCP tool name length: model API enforces 64-char limit on tool names.
     Long catalog/schema/index names cause BAD_REQUEST errors. Use short
     index names (configured via vs_index_name in config.yml).
  2. Service principal permissions: the app's SP needs CAN_RUN on the
     Genie Space, CAN_USE on its SQL warehouse, and SELECT on the VS index.
  3. connect_healthy_mcp_servers() gracefully skips unavailable servers
     rather than crashing the whole request.
"""
import logging
from contextlib import AsyncExitStack
from datetime import datetime
from typing import AsyncGenerator

import mlflow
from agents import Agent, Runner, function_tool, set_default_openai_api, set_default_openai_client
from agents.tracing import set_trace_processors
from databricks.sdk import WorkspaceClient
from databricks_openai import AsyncDatabricksOpenAI
from databricks_openai.agents import McpServer
from mlflow.genai.agent_server import invoke, stream
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
)

from agent_server.history import normalize_history_items
from agent_server.utils import (
    build_mcp_url,
    get_session_id,
    get_user_workspace_client,
    process_agent_stream_events,
)

logger = logging.getLogger(__name__)

# NOTE: this will work for all databricks models OTHER than GPT-OSS, which uses a slightly different API
set_default_openai_client(AsyncDatabricksOpenAI())
set_default_openai_api("chat_completions")
set_trace_processors([])  # only use mlflow for trace processing
mlflow.openai.autolog()
logging.getLogger("mlflow.utils.autologging_utils").setLevel(logging.ERROR)


@function_tool
def get_current_time() -> str:
    """Get the current date and time."""
    return datetime.now().isoformat()


async def init_mcp_server(workspace_client: WorkspaceClient):
    return McpServer(
        url=build_mcp_url("/api/2.0/mcp/functions/system/ai", workspace_client=workspace_client),
        name="system.ai UC function MCP server",
        workspace_client=workspace_client,
    )


# ---------------------------------------------------------------------------
# Workshop-specific MCP servers
# Replace these values with your own from config.yml:
#   GENIE_SPACE_ID  <- genie_agent_id
#   VS_INDEX_PATH   <- {uc_catalog}/{uc_schema}/{vs_index_name}{table_postfix}
# ---------------------------------------------------------------------------
GENIE_SPACE_ID = "<your_genie_space_id>"
VS_INDEX_PATH = "<your_catalog>/<your_schema>/<vs_index_name><postfix>"


async def init_genie_mcp_server(workspace_client: WorkspaceClient):
    return McpServer(
        url=build_mcp_url(f"/api/2.0/mcp/genie/{GENIE_SPACE_ID}", workspace_client=workspace_client),
        name="GlowMart Genie Agent",
        workspace_client=workspace_client,
    )


async def init_ai_search_mcp_server(workspace_client: WorkspaceClient):
    return McpServer(
        url=build_mcp_url(f"/api/2.0/mcp/ai-search/{VS_INDEX_PATH}", workspace_client=workspace_client),
        name="GlowMart Document Search",
        workspace_client=workspace_client,
    )


async def connect_healthy_mcp_servers(
    stack: AsyncExitStack, servers: list[McpServer]
) -> tuple[list[McpServer], list[str]]:
    """Connect each MCP server and verify it can actually list its tools.

    The Agents SDK lists each server's tools lazily inside ``Runner.run``, so a server that
    connects but fails at list time (e.g. an unauthorized Genie space) would otherwise crash
    the whole request — including unrelated turns. We list tools here, per server: healthy
    servers are kept; any that fails to connect OR to list is dropped and its name returned,
    so the agent runs with whatever is available instead of erroring out.

    Returns (healthy_servers, unavailable_names).
    """
    healthy: list[McpServer] = []
    unavailable: list[str] = []
    for server in servers:
        name = getattr(server, "name", "MCP server")
        try:
            connected = await stack.enter_async_context(server)
            await connected.list_tools()  # forces the connectivity + authorization check now
            healthy.append(connected)
        except Exception:
            logger.warning("MCP server %r unavailable; continuing without it.", name, exc_info=True)
            unavailable.append(name)
    return healthy, unavailable


# ---------------------------------------------------------------------------
# Agent instructions — routing guidance for MCP tools
# Without this, the model tends to call whichever MCP tool it discovers first
# rather than matching the question type to the right backend.
# ---------------------------------------------------------------------------
AGENT_INSTRUCTIONS = """
You are a helpful assistant for GlowMart, a beauty supply retailer.

You have access to the following tools — use the right one for each question:

- **GlowMart Genie Agent**: Use for structured data questions about sales, orders, revenue,
  inventory, customers, stores, and products. This connects to GlowMart's curated analytics
  data. Examples: "What is total revenue by category?", "Which stores need reorders?",
  "Top 10 customers by spend."

- **GlowMart Document Search**: Use for questions about company policies, product documentation,
  or any unstructured knowledge base content. Examples: "What is the return policy?",
  "Tell me about the loyalty program rules."

- **get_current_time**: Use when the user asks for the current date or time.

When answering, cite which tool you used. If a question spans both structured data and documents,
use both tools and synthesize the results.
"""


def create_agent(mcp_servers: list[McpServer] | None = None) -> Agent:
    return Agent(
        name="GlowMart Assistant",
        instructions=AGENT_INSTRUCTIONS,
        model="databricks-gpt-5-2",
        tools=[get_current_time],
        mcp_servers=mcp_servers or [],
    )


@invoke()
async def invoke_handler(request: ResponsesAgentRequest) -> ResponsesAgentResponse:
    if session_id := get_session_id(request):
        mlflow.update_current_trace(metadata={"mlflow.trace.session": session_id})
    async with AsyncExitStack() as stack:
        wc = WorkspaceClient()
        servers, unavailable = await connect_healthy_mcp_servers(
            stack,
            [
                await init_mcp_server(wc),
                await init_genie_mcp_server(wc),
                await init_ai_search_mcp_server(wc),
            ],
        )
        agent = create_agent(mcp_servers=servers)
        messages = normalize_history_items([i.model_dump() for i in request.input])
        result = await Runner.run(agent, messages)
        return ResponsesAgentResponse(output=[item.to_input_item() for item in result.new_items])


@stream()
async def stream_handler(
    request: ResponsesAgentRequest,
) -> AsyncGenerator[ResponsesAgentStreamEvent, None]:
    if session_id := get_session_id(request):
        mlflow.update_current_trace(metadata={"mlflow.trace.session": session_id})
    async with AsyncExitStack() as stack:
        wc = WorkspaceClient()
        servers, unavailable = await connect_healthy_mcp_servers(
            stack,
            [
                await init_mcp_server(wc),
                await init_genie_mcp_server(wc),
                await init_ai_search_mcp_server(wc),
            ],
        )
        agent = create_agent(mcp_servers=servers)
        messages = normalize_history_items([i.model_dump() for i in request.input])
        result = Runner.run_streamed(agent, input=messages)

        async for event in process_agent_stream_events(result.stream_events()):
            yield event
