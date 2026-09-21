# Agent Workshop — Assistant Instructions

This file provides context for Databricks Assistant (Genie Code) to help workshop participants build, run, and troubleshoot the agent workshop materials.

## Project Overview

This workshop teaches agentic AI development on Databricks through a hands-on beauty supply retail scenario ("GlowMart"). Participants build a multi-agent system with RAG, text-to-SQL (Genie), and tool calling.

## Directory Structure

```
agent_workshop/
├── AGENT.md              ← You are here (instructions for Databricks Assistant)
├── README.md             ← Workshop agenda and module descriptions
├── config.yml            ← Shared config: catalog, schema, prefix/postfix, volume, row counts
├── data/
│   ├── 01_customers      ← Notebook: synthetic customer profiles
│   ├── 02_products       ← Notebook: beauty product catalog
│   ├── 03_stores         ← Notebook: store locations
│   ├── 04_orders         ← Notebook: order transactions (PySpark-native)
│   ├── 05_order_items    ← Notebook: line items per order
│   ├── 06_inventory      ← Notebook: stock levels per store
│   ├── run_all           ← Notebook: orchestrates all 6 data notebooks
│   ├── cleanup           ← Notebook: drops all workshop tables
│   └── genie_config.md        ← Genie Space text instruction + structured config: join snippets, SQL measures, filters, starter questions
├── documents/
│   ├── *.pdf                 ← GlowMart PDF documents (return policy, skincare guide, etc.)
│   └── upload_to_volume      ← Notebook: copies PDFs to a Unity Catalog Volume
├── process_documents/
│   ├── 01_parse_and_chunk    ← Notebook: ai_parse_document + ai_prep_search → two tables
│   └── 02_create_vector_index ← Notebook: Vector Search endpoint + Delta Sync index
├── langgraph_agent/              ← LangGraph supervisor (notebook-only, step 9)
│   ├── config.py                 ← Reads config.yml, exports resource values
│   ├── supervisor.py             ← Compiles the full supervisor graph
│   ├── agents/genie/             ← GenieAgent text-to-SQL specialist
│   └── agents/rag/               ← DatabricksVectorSearch RAG specialist
└── agents_on_apps/
    ├── agent_mcp_reference.py         ← Reference: tool-calling agent with MCP (step 8d)
    ├── agent_supervisor_reference.py  ← Reference: supervisor with handoffs (step 8e)
    ├── history_reference.py           ← Patched history.py: fixes supervisor multi-turn bug (step 8e)
    └── test_supervisor                ← Notebook: test supervisor without app shell
```

## Configuration

All notebooks read from `config.yml` at the project root (`agent_workshop/config.yml`). The config path is resolved dynamically at runtime by navigating up from the notebook location to the project root — no hardcoded workspace paths. Participants must edit `config.yml` before running anything.

| Key | Purpose | Example |
|---|---|---|
| `uc_catalog` | Unity Catalog catalog for all tables | `my_catalog` |
| `uc_schema` | Schema within the catalog | `workshop_schema` |
| `table_prefix` | Prefix prepended to every table name (groups workshop tables together) | `agent_demo` |
| `table_postfix` | Suffix appended to every table name (avoids collisions in shared catalogs) | `_jdoe` |
| `num_customers` | Number of customer records to generate | `5000` |
| `num_products` | Number of products in the catalog | `500` |
| `num_stores` | Number of store locations | `50` |
| `num_orders` | Number of order transactions | `100000` |
| `volume_name` | UC Volume for PDF documents (used by the RAG module) | `company_pdfs` |
| `parsed_documents_table_name` | Table for raw ai_parse_document output | `parsed_docs` |
| `document_chunks_table_name` | Table for ai_prep_search chunks (Vector Search source) | `document_chunks` |
| `vs_endpoint_name` | Vector Search endpoint name | `agent_demo_vs_endpoint` |
| `vs_index_name` | Short Vector Search index name (MCP tool name must stay under 64 chars) | `vs_index` |
| `embedding_model` | Embedding model endpoint for managed embeddings | `databricks-gte-large-en` |
| `genie_agent_id` | Genie Space ID (add after provisioning in step 6b) | `01f1ad56...` |
| `app_code_dir` | Databricks App source folder path (add after deploying in step 8b) | `/Users/<you>/databricks_apps/<app>_<ts>/<app>` |

### Table Naming Convention

Tables are named `{catalog}.{schema}.{prefix}_{table}{postfix}`, e.g.:
- `my_catalog.workshop_schema.agent_demo_customers_jdoe`
- `my_catalog.workshop_schema.agent_demo_orders_jdoe`

## Execution Order

Notebooks must be run in dependency order:

```
Phase 1 (independent — run in any order):
  01_customers
  02_products
  03_stores
  04_orders

Phase 2 (depends on Phase 1):
  05_order_items  → requires: orders + products tables
  06_inventory    → requires: stores + products tables
```

Each notebook:
1. Reads `config.yml` from the project root
2. Generates synthetic data
3. Creates the schema if needed (`CREATE SCHEMA IF NOT EXISTS`)
4. Writes to Delta (`mode=overwrite`, safe to re-run)
5. Applies table and column descriptions (COMMENT ON TABLE / ALTER COLUMN COMMENT)
6. Displays a verification query

### Running All Notebooks

When asked to "run all data notebooks" or "set up the data":
1. **Prerequisite**: Read `config.yml` and confirm `uc_catalog`, `uc_schema`, and `table_postfix` are set to real values (not placeholders). If they look like defaults or placeholders, ask the participant to update them first.
2. Open `01_customers` and run all cells
3. Run `02_products`, `03_stores`, `04_orders` (order doesn't matter)
4. After all Phase 1 notebooks succeed, run `05_order_items`
5. Run `06_inventory`
6. Confirm all 6 tables exist by querying the target catalog.schema

### Notebook Execution Mechanism

The workshop instructions notebook is the participant's home base. When asked to run a different notebook (data generation, upload_to_volume, document processing), the assistant **cannot execute cells remotely** from another page. Follow this approach:

1. **Navigate to the target notebook** using `openAsset` with `assetType="notebook"` and the notebook's workspace ID.
2. **Include a non-empty `continueMessage`** that tells the destination agent what to do (e.g., `"Run all code cells in this notebook to generate synthetic customer data. After completion, navigate back to notebook 1488764113540926."`)
3. The agent on the destination page uses `runNotebookCells` to execute cells.
4. After the notebook completes, navigate back to the workshop instructions notebook.

For multi-notebook sequences (e.g., running all 6 data notebooks), navigate to each notebook in order, run its cells, then proceed to the next.

**Why not `executeCode` with `dbutils.notebook.run()`?**
This approach is often blocked by the auto-approval layer when notebooks contain DDL statements (`CREATE TABLE`, `CREATE VOLUME`, `CREATE SCHEMA`), which most workshop notebooks do. The `openAsset` + `continueMessage` handoff is the reliable path.

**Why not `runNotebookCells` from the workshop notebook page?**
`runNotebookCells` only works on the **currently active** notebook. You cannot remotely trigger cell execution in a notebook that isn't the open page.

**Fallback — participant runs manually:**
If execution is blocked or fails, navigate to the target notebook with `openAsset` and tell the participant to run the cells themselves. The cells are idempotent (`mode=overwrite`, `IF NOT EXISTS`) so re-running is always safe.

## Data Model — GlowMart

GlowMart is a fictional beauty supply retailer with online and brick-and-mortar stores.

### Star Schema

```
                    ┌────────────┐
                    │  customers │
                    └─────┬──────┘
                          │ customer_id
                          │
┌──────────┐    ┌─────────┴──────────┐    ┌────────┐
│  stores  ├────┤      orders        ├────┤  (channel: online → store_id IS NULL)
└─────┬────┘    └─────────┬──────────┘    └────────┘
      │ store_id          │ order_id
      │                   │
      │           ┌───────┴──────────┐
      │           │   order_items    │
      │           └───────┬──────────┘
      │                   │ product_id
      │                   │
      │           ┌───────┴──────────┐
      ├───────────┤    products      │
      │           └──────────────────┘
      │ store_id + product_id
┌─────┴────────┐
│  inventory   │
└──────────────┘
```

### Key Business Rules

- **Revenue**: `order_items.unit_price * order_items.quantity * (1 - order_items.discount_pct)` — NOT `orders.total_amount`
- **Online orders**: `store_id IS NULL` and `channel = 'online'`
- **Loyalty tiers**: Bronze (40%), Silver (30%), Gold (20%), Platinum (10%)
- **Store types**: Flagship (~90% of products), Standard (~70%), Express (~40%)
- **Order dates**: 2023-01-01 to 2024-12-31
- **Customer signups**: 2019-01-01 to 2024-12-31

## Genie Space Setup (Participant-Driven)

The Genie Space is created manually by participants as a learning exercise — do NOT automate this step. After tables are created, guide participants to:
1. Create a Genie Space in the workspace UI
2. Set the space description (see `data/genie_config.md`)
3. Add all 6 tables (using the prefixed/postfixed names from config)
4. Copy the text instruction section from `data/genie_config.md` as a General Instruction
5. Add the 6 join snippets from `data/genie_config.md`
6. Add the 3 SQL measure/filter snippets from `data/genie_config.md`
7. Add column synonyms from `data/genie_config.md`
8. Add starter questions from `data/genie_config.md`
9. Test with the starter questions

Note: Table and column descriptions are already applied by the data notebooks (step 5 in each notebook). Genie reads these automatically — no manual entry needed.

The assistant's role here is limited to:
- Confirming all tables exist and are queryable
- Providing the fully qualified table names from config
- Pointing participants to `data/genie_config.md` for structured configuration

## Document Processing Pipeline

The RAG module uses a three-step pipeline: upload → parse & chunk → index.

### Step 1: Upload PDFs to Volume

When asked to "upload the PDFs" or "set up the RAG documents":
1. Run `documents/upload_to_volume` — copies all PDFs from `documents/` to the UC Volume

### Step 2: Parse and Chunk Documents

When asked to "parse the documents" or "prepare documents for vector search":
1. Run `process_documents/01_parse_and_chunk` — this does four things:
   - Parses all PDFs with `ai_parse_document` → persists `{prefix}_{parsed_documents_table_name}{postfix}` table
   - Chunks with `ai_prep_search` → persists `{prefix}_{document_chunks_table_name}{postfix}` table
   - Enables Change Data Feed on the chunks table
   - Adds a PRIMARY KEY constraint on `chunk_id`
2. Both tables are persisted because parsing is expensive; re-chunking doesn't require re-parsing

### Step 3: Create Vector Search Index

When asked to "create the vector index" or "set up vector search":
1. Run `process_documents/02_create_vector_index` — this:
   - Creates or reuses a Vector Search endpoint (`vs_endpoint_name` from config)
   - Creates a Delta Sync index with managed embeddings on the chunks table
   - Waits for the index to sync and become ready
   - Runs a test similarity query
2. **Prerequisite**: `01_parse_and_chunk` must be run first (the chunks table must exist with CDF and PK)
3. Endpoint creation + index sync can take ~40 minutes total for the first run
4. The notebook checks for existing endpoints/indexes first and reuses them if found

### Execution Order

```
upload_to_volume → 01_parse_and_chunk → 02_create_vector_index
```

## Cleanup

When asked to "clean up" or "tear down the workshop data":
1. Run the `data/cleanup` notebook — it drops all 6 tables using the postfixed names from config
2. Tables are dropped in reverse dependency order (order_items and inventory first, then the rest)
3. The schema drop is commented out by default — only uncomment if the participant owns the schema and no other tables exist in it
4. Do NOT drop the schema without explicit participant confirmation

## Troubleshooting

| Issue | Fix |
|---|---|
| `FileNotFoundError: config.yml` | Ensure `config.yml` exists at the project root (`agent_workshop/config.yml`) |
| `AnalysisException: Table not found` for 05/06 | Run Phase 1 notebooks first |
| Permission errors on catalog/schema | Verify `uc_catalog` and `uc_schema` in config.yml — participant needs CREATE TABLE permission |
| Duplicate table names | Each participant should use a unique `table_postfix` value |
| `ai_prep_search` PERMISSION_DENIED | A workspace admin must enable the **AI Prep Search Preview** in Admin Settings → Previews |
| PK constraint fails: `column is nullable` | `ai_prep_search` output columns are nullable — run `ALTER COLUMN chunk_id SET NOT NULL` before adding the PK |
| `'str' object has no attribute 'value'` in VS SDK | Use SDK enum types (`EndpointType.STANDARD`, `VectorIndexType.DELTA_SYNC`) not plain strings |
| `'dict' object has no attribute 'as_dict'` in VS SDK | Use typed SDK objects (`DeltaSyncVectorIndexSpecRequest`, `EmbeddingSourceColumn`) not plain dicts |
| Vector Search endpoint not found | Import `NotFound` from `databricks.sdk.errors` for proper exception handling |
| Supervisor: `tool_calls must be followed by tool messages` on 2nd request | See **Fixing history.py for supervisor multi-turn** section below |
| MLflow trace `PERMISSION_DENIED` on `_otel_spans` / `_otel_annotations` tables | The app's service principal needs UC grants: `USE CATALOG`, `USE SCHEMA`, and `SELECT, MODIFY` on the auto-created trace tables (`{experiment_id}_otel_spans`, `{experiment_id}_otel_annotations`) in your catalog.schema. The `databricks.yml` `CAN_MANAGE` on the experiment alone is not sufficient. |

### Fixing history.py for supervisor multi-turn

**Symptom**: The supervisor agent works on the first message but throws `An assistant message with 'tool_calls' must be followed by tool messages responding to each 'tool_call_id'` on the second or later messages.

**Root cause**: The supervisor uses `handoffs`, which internally create `function_call` and `function_call_output` items in the conversation. On the next user message, the chat UI replays the full history including these items. The `call_id` values don't survive the round-trip through the UI, so the model sees an assistant message with `tool_calls` that has no matching tool response — triggering the 400 error.

**Fix**: In `agent_server/history.py`, find the function that iterates over the message history (currently `normalize_history_items`, but the name may change in future templates). At the **top of the loop body**, before any other processing, add a guard that skips `function_call` and `function_call_output` items:

```python
# Inside the for-loop that iterates over messages:
for m in messages:
    # --- ADD THIS BLOCK at the top of the loop ---
    # Strip function_call / function_call_output items from replayed history.
    # The supervisor's handoff tool_calls don't survive the round-trip through
    # the chat UI — call_id pairs are lost, causing orphaned tool_calls errors.
    # The SDK regenerates these for the current turn; only user messages and
    # final assistant text responses are needed for conversational context.
    if m.get("type") in ("function_call", "function_call_output"):
        continue
    # --- END OF ADDED BLOCK ---

    # ... rest of existing loop body ...
```

The key pattern: check `m.get("type")` against both `"function_call"` and `"function_call_output"`, and `continue` to skip them. This is safe because the OpenAI Agents SDK regenerates tool calls for the current turn — only user/assistant text history is needed for conversational context.

If the template has been restructured and there is no message-iteration loop, the same filter must be applied wherever the incoming `messages` list is consumed before being passed to `Runner.run()` or equivalent.

## Enhancing the Default Agent Template with MCP Servers

After deploying the default “deploy your own agent” template (step 8), participants add Genie and AI Search capabilities to the existing OpenAI Agents SDK agent using Databricks managed MCP servers. This is a quick, low-code enhancement that demonstrates how MCP works — before the supervisor step (8e) and the optional LangGraph tutorial (step 9).

### What Are Databricks Managed MCP Servers?

Model Context Protocol (MCP) is an open standard that lets agents discover and call tools via a URL. Databricks provides managed MCP servers for workspace resources — no infrastructure to deploy. When the agent connects to an MCP server, it automatically discovers available tools and their schemas.

The default agent template already includes scaffolding for MCP (the `init_mcp_server`, `connect_healthy_mcp_servers`, and `McpServer` imports). Participants just need to add new server initializers and uncomment the wiring in the handlers.

### Available Managed MCP Servers

| Server | URL Pattern | OAuth Scope |
|---|---|---|
| Genie Agent (scoped to one space) | `/api/2.0/mcp/genie/{genie_space_id}` | `genie` |
| AI Search (Vector Search index) | `/api/2.0/mcp/ai-search/{catalog}/{schema}/{index_name}` | `ai-search` |
| Unity Catalog Functions | `/api/2.0/mcp/functions/{catalog}/{schema}/{function_name}` | `unity-catalog` |
| Genie One (workspace-wide) | `/api/2.0/mcp/genie` | `genie` |
| Databricks SQL | `/api/2.0/mcp/sql` | `sql` |

For this workshop, participants wire in the **Genie Agent** and **AI Search** servers.

### Step-by-Step: Adding MCP Servers to agent.py

#### 1. Add constants for the Genie Space and Vector Search index

```python
GENIE_SPACE_ID = "<your_genie_space_id>"  # from genie_agent_id in config.yml
VS_INDEX_PATH = "<catalog>/<schema>/<vs_index_name><postfix>"  # forward slashes, not dots
```

Note: the MCP URL uses forward-slash separators (`catalog/schema/index`), not the dot notation used by the SDK (`catalog.schema.index`).

#### 2. Add MCP server initializer functions

```python
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
```

#### 3. Wire the servers into both handlers

In both `invoke_handler` and `stream_handler`, replace the bare `create_agent()` call with:

```python
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
```

The `connect_healthy_mcp_servers` function health-checks each server at connect time. If one server is unavailable (e.g., permissions not yet granted), the agent continues with the remaining servers instead of crashing.

#### 4. Update agent name and instructions

The default template ships with `name="Agent"` and `instructions="You are a helpful assistant."`. Both must be updated:

* Rename the agent to `"GlowMart Assistant"` for clearer trace labeling in MLflow.
* Replace the instructions with routing guidance so the model matches question types to the right MCP backend. Without this, the model tends to call whichever MCP tool it discovers first.

```python
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
```

### Tool Name Length Limitation (64 Characters)

MCP servers auto-generate tool names from the resource path. The model API enforces a **64-character limit** on tool names. Long catalog/schema/index names can easily exceed this.

For example, an index named `my_catalog.my_schema.agent_demo_document_chunks_index_jdoe` produces a tool name of 79 characters — causing a `BAD_REQUEST` error:

```
Invalid 'messages[4].tool_calls[0].function.name': string too long.
Expected a string with maximum length 64, but got a string with length 79.
```

**Solution**: The workshop uses a short, config-driven index name convention: `vs_index{postfix}` (e.g., `vs_index_mlc`). This is configured via the `vs_index_name` key in `config.yml` and produces MCP tool names well under 64 characters.

If participants encounter this error with their own catalog/schema names, the alternatives are:
1. Use a shorter index name (preferred for MCP)
2. Replace the MCP server with a direct `@function_tool` that calls the Vector Search SDK (gives full control over the tool name)

### Service Principal Permissions for MCP

The app’s service principal needs these permissions for the MCP servers to connect:

| Permission | Target | MCP Server |
|---|---|---|
| `CAN_RUN` | Genie Space | Genie Agent MCP |
| `CAN_USE` | SQL warehouse backing the Genie Space | Genie Agent MCP |
| `SELECT` | Vector Search index table | AI Search MCP |
| `USE CATALOG` + `USE SCHEMA` | Catalog and schema containing the index | AI Search MCP |

Grant these in `databricks.yml` or manually via the workspace UI. The `connect_healthy_mcp_servers` function logs a warning and skips any server where permissions are missing.

### Reference Implementation

See `agents_on_apps/agent_mcp_reference.py` for the complete working `agent.py` with all three MCP servers wired in.

---

## Agent Architecture Progression

The workshop walks participants through three agent architectures of increasing complexity, all using the same serving shell (`start_server.py`, `history.py`, `utils.py`). Each architecture lives in its own file inside `agent_server/`, and `agent.py` acts as a thin router that re-exports from the active one.

### File-Swapping Pattern

`agent_server/agent.py` is a one-line import that selects the active architecture:

```python
# agent.py — Architecture switcher
# To switch: comment out the active import and uncomment the desired one.
# Then redeploy the app.

# --- Active architecture ---
from agent_server.agent_tool_calling import invoke_handler, stream_handler  # noqa: F401

# --- Alternative architectures ---
# from agent_server.agent_supervisor import invoke_handler, stream_handler  # noqa: F401
```

The `@invoke()` and `@stream()` decorators register at import time, so the re-export works — `mlflow.genai.agent_server` discovers the handlers regardless of which module defines them. Switching architectures is a one-line change followed by a redeploy.

### Three-Step Progression

| Step | Architecture | File | Key Concept |
|---|---|---|---|
| 8d | Tool-calling agent | `agent_tool_calling.py` | Single agent, all MCP tools flattened, routing via instructions |
| 8e | Supervisor agent | `agent_supervisor.py` | Specialist sub-agents with `handoffs`, same SDK |
| 9 | LangGraph supervisor | `langgraph_agent/` (notebook import) | Same pattern, different framework, notebook-only |

The progression from 8d → 8e isolates the architectural change (tool-calling vs. supervisor) without also changing frameworks. Step 9 then shows what the same supervisor pattern looks like in LangGraph — more code, but more control over graph topology and state. The LangGraph implementation lives in `langgraph_agent/` and is imported directly into the workshop notebook (not deployed on apps).

### Supervisor Architecture (Step 8e)

The supervisor splits the single tool-calling agent into specialist sub-agents connected via `handoffs`:

```
GlowMart Assistant (supervisor)
  ├── handoff → GlowMart Data Analyst
  │     └── MCP: Genie Agent server (structured data)
  ├── handoff → GlowMart Document Expert
  │     └── MCP: AI Search server (document retrieval)
  └── Direct tool: get_current_time
```

Key differences from the tool-calling agent:

| Aspect | Tool-Calling (8d) | Supervisor (8e) |
|---|---|---|
| MCP server assignment | All servers on one agent | Split across specialists |
| Routing mechanism | Model picks tools from flat list | Supervisor delegates via `handoffs` |
| Instructions | Single instruction set with routing hints | Focused instructions per specialist |
| system.ai UC functions | Included | Dropped (cleaner demo) |
| `create_agent()` signature | `create_agent(mcp_servers=...)` | `create_supervisor(genie_mcp_servers=..., doc_mcp_servers=...)` |

The supervisor's instructions explicitly tell it to delegate rather than answer directly:

```
Routing rules:
1. Identify which specialist should handle the question and hand off to them.
2. If a question needs both data and documents, hand off to each specialist
   sequentially and synthesize their answers.
3. Do NOT answer data or document questions yourself — always delegate.
```

Each specialist gets focused instructions (e.g., “Always include specific numbers” for the data analyst, “Always cite the source document” for the document expert) that would conflict if combined in a single agent.

In the handlers, MCP servers are connected independently per specialist:

```python
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
```

### When to Choose Each Architecture

* **Tool-calling**: Few tools, no instruction conflicts, simplest code path. Good for demos and prototypes.
* **Supervisor (OpenAI SDK)**: Specialists need different instructions or model configs, want isolated contexts, minimal additional code. Good for production agents with 2–5 domains.
* **LangGraph supervisor** (notebook-only): Need fine-grained control over graph topology, conditional edges, custom state management, or complex multi-step workflows. More code but maximum flexibility. See `langgraph_agent/` directory.

### Reference Implementations

The `agents_on_apps/` directory contains reference implementations and patches for the app architectures:

| File | Architecture | Notes |
|---|---|---|
| `agent_mcp_reference.py` | Tool-calling agent | Placeholder values for participant config |
| `agent_supervisor_reference.py` | Supervisor with handoffs | Placeholder values, same SDK |
| `history_reference.py` | Patched history.py | Fixes supervisor multi-turn orphaned tool_calls bug |

---

## LangGraph Supervisor (Notebook-Only)

The LangGraph supervisor implementation lives in `langgraph_agent/` and is imported directly into the workshop notebook. It is NOT deployed on Databricks Apps — the app only supports tool-calling (8d) and supervisor (8e) architectures via the OpenAI Agents SDK.
