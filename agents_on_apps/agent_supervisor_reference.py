"""Supervisor Agent — OpenAI Agents SDK with Handoffs — Reference Implementation

This is the working agent.py that converts the tool-calling MCP agent into a
supervisor architecture using the OpenAI Agents SDK's native `handoffs` mechanism.

Architecture:
  supervisor (GlowMart Assistant)
    ├── handoff → genie_agent (GlowMart Data Analyst)
    │     └── MCP: Genie Agent server
    └── handoff → doc_agent (GlowMart Document Expert)
          └── MCP: AI Search server

Key changes from agent_tool_calling.py (the tool-calling version):
  1. Split MCP servers across specialist sub-agents instead of one flat agent
  2. Each specialist has focused instructions scoped to its domain
  3. Supervisor routes via `handoffs` — it never calls MCP tools directly
  4. Supervisor keeps `get_current_time` as a direct tool
  5. Dropped the system.ai UC functions MCP (not needed for this demo)

Serving shell (unchanged from template):
  - start_server.py  — mlflow.genai.agent_server.AgentServer
  - history.py       — normalize_history_items()
  - utils.py         — get_session_id(), get_user_workspace_client(),
                       build_mcp_url(), process_agent_stream_events()

When to use this over tool-calling:
  - Specialists need conflicting instructions (e.g., "only answer data questions"
    vs. "only answer document questions")
  - You want isolated conversation contexts per specialist
  - You want different model configs per specialist (not done here, but easy to add)
  - You want clearer MLflow traces showing which specialist handled each request
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

set_default_openai_client(AsyncDatabricksOpenAI())
set_default_openai_api("chat_completions")
set_trace_processors([])  # only use mlflow for trace processing
mlflow.openai.autolog()
logging.getLogger("mlflow.utils.autologging_utils").setLevel(logging.ERROR)


@function_tool
def get_current_time() -> str:
    """Get the current date and time."""
    return datetime.now().isoformat()


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

    Returns (healthy_servers, unavailable_names).
    """
    healthy: list[McpServer] = []
    unavailable: list[str] = []
    for server in servers:
        name = getattr(server, "name", "MCP server")
        try:
            connected = await stack.enter_async_context(server)
            await connected.list_tools()
            healthy.append(connected)
        except Exception:
            logger.warning("MCP server %r unavailable; continuing without it.", name, exc_info=True)
            unavailable.append(name)
    return healthy, unavailable


# ---------------------------------------------------------------------------
# Supervisor instructions — routing guidance
# ---------------------------------------------------------------------------
SUPERVISOR_INSTRUCTIONS = """
You are the GlowMart Assistant, a supervisor that routes questions to specialist agents.

You coordinate two specialists:

- **GlowMart Data Analyst**: Handles structured data questions about sales, orders,
  revenue, inventory, customers, stores, and products. Hand off any question that
  needs numbers, rankings, trends, or aggregations from the retail database.

- **GlowMart Document Expert**: Handles questions about company policies, product
  documentation, and knowledge base content. Hand off any question about rules,
  procedures, or unstructured information.

Routing rules:
1. Identify which specialist should handle the question and hand off to them.
2. If a question needs both data and documents, hand off to each specialist
   sequentially and synthesize their answers.
3. Do NOT answer data or document questions yourself — always delegate.
4. You may answer general greetings or questions about your capabilities directly.
5. Use get_current_time when the user asks for the current date or time.
"""

GENIE_AGENT_INSTRUCTIONS = """
You are a data analyst for GlowMart, a beauty supply retailer.

Use the Genie tool to answer questions about sales, orders, revenue, inventory,
customers, stores, and products. This connects to GlowMart's curated analytics data.

Always include specific numbers and data in your response. If Genie returns SQL,
mention the key query logic so the user understands how the answer was derived.
"""

DOC_AGENT_INSTRUCTIONS = """
You are a document specialist for GlowMart, a beauty supply retailer.

Use the document search tool to answer questions about company policies, product
documentation, return procedures, loyalty program rules, and other knowledge base
content.

Always cite the source document in your response so the user can verify the information.
"""


# ---------------------------------------------------------------------------
# Agent factory — builds the supervisor + specialist agents
# ---------------------------------------------------------------------------
def create_supervisor(
    genie_mcp_servers: list[McpServer] | None = None,
    doc_mcp_servers: list[McpServer] | None = None,
) -> Agent:
    """Build the supervisor agent with specialist sub-agents.

    Each specialist gets its own MCP servers and focused instructions.
    The supervisor routes between them via handoffs.
    """
    genie_agent = Agent(
        name="GlowMart Data Analyst",
        instructions=GENIE_AGENT_INSTRUCTIONS,
        model="databricks-gpt-5-5",
        mcp_servers=genie_mcp_servers or [],
    )

    doc_agent = Agent(
        name="GlowMart Document Expert",
        instructions=DOC_AGENT_INSTRUCTIONS,
        model="databricks-gpt-5-5",
        mcp_servers=doc_mcp_servers or [],
    )

    return Agent(
        name="GlowMart Assistant",
        instructions=SUPERVISOR_INSTRUCTIONS,
        model="databricks-gpt-5-5",
        tools=[get_current_time],
        handoffs=[genie_agent, doc_agent],
    )


# ---------------------------------------------------------------------------
# MLflow agent server handlers
# ---------------------------------------------------------------------------
@invoke()
async def invoke_handler(request: ResponsesAgentRequest) -> ResponsesAgentResponse:
    if session_id := get_session_id(request):
        mlflow.update_current_trace(metadata={"mlflow.trace.session": session_id})
    async with AsyncExitStack() as stack:
        wc = WorkspaceClient()
        # Connect each specialist's MCP servers independently
        genie_servers, _ = await connect_healthy_mcp_servers(
            stack, [await init_genie_mcp_server(wc)]
        )
        doc_servers, _ = await connect_healthy_mcp_servers(
            stack, [await init_ai_search_mcp_server(wc)]
        )
        agent = create_supervisor(
            genie_mcp_servers=genie_servers,
            doc_mcp_servers=doc_servers,
        )
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
        genie_servers, _ = await connect_healthy_mcp_servers(
            stack, [await init_genie_mcp_server(wc)]
        )
        doc_servers, _ = await connect_healthy_mcp_servers(
            stack, [await init_ai_search_mcp_server(wc)]
        )
        agent = create_supervisor(
            genie_mcp_servers=genie_servers,
            doc_mcp_servers=doc_servers,
        )
        messages = normalize_history_items([i.model_dump() for i in request.input])
        result = Runner.run_streamed(agent, input=messages)

        async for event in process_agent_stream_events(result.stream_events()):
            yield event
