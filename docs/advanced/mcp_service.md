# MCP Service

Expose your SQLModel entity graph to AI agents via the Model Context Protocol. An AI agent can query your data through GraphQL — with schema discovery, query execution, and relationship traversal all handled automatically.

## Step 1: Create an MCP Server

Install the MCP dependency first:

```bash
pip install nexusx[fastmcp]
```

Then create a server from your SQLModel base class:

```python
from nexusx.mcp import create_simple_mcp_server

mcp = create_simple_mcp_server(
    base=SQLModel,
    name="My API",
    session_factory=async_session,  # Required for database queries
)
```

That's it — your AI agent now has three tools:

| Tool | Purpose |
|------|---------|
| `get_schema()` | Get the GraphQL schema |
| `graphql_query(query)` | Execute a GraphQL query |
| `graphql_mutation(mutation)` | Execute a GraphQL mutation |

The AI agent can discover your schema, then query it with full relationship traversal — the same DataLoader batch loading that powers GraphQL mode works under the hood.

## Step 2: Run the Server

Two transport modes:

```python
# stdio — for CLI-based AI tools (Claude Desktop, Cursor)
mcp.run()

# HTTP — for web-based AI agents running as a separate service
mcp.run(transport="sse", host="0.0.0.0", port=8003)
```

!!! tip
    Use **stdio** when integrating with desktop AI tools. Use **HTTP** when your AI agent runs as a separate service.

## Step 3: Multi-App Mode

When your AI agent needs to work across multiple databases or domains:

```python
from nexusx.mcp import create_mcp_server

mcp = create_mcp_server(
    apps=[
        {"name": "blog", "base": BlogBase, "description": "Blog API"},
        {"name": "shop", "base": ShopBase, "description": "Shop API"},
    ],
    name="Multi-App API",
    session_factory=async_session,
)
mcp.run()
```

Multi-app adds app-level navigation tools:

| Tool | Purpose |
|------|---------|
| `list_apps()` | List all available apps |
| `list_queries(app_name)` | List queries for an app |
| `get_query_schema(name, app_name)` | Get query schema |
| `graphql_query(query, app_name)` | Execute query |

!!! tip
    Use `create_simple_mcp_server` for single-app scenarios — fewer tool calls, simpler interaction. Only reach for `create_mcp_server` when the AI agent genuinely needs to cross domain boundaries.

## Recap

- `create_simple_mcp_server` — single app, 3 tools, get started in seconds
- `create_mcp_server` — multiple apps, app-level navigation for cross-domain queries
- Both support `stdio` (CLI) and `sse` (HTTP) transport
- `session_factory` is required — the MCP server executes real database queries

## Next Steps

- [UseCase Service](./use_case_service.md) — Business logic services for MCP + REST dual-mode
- [GraphQL Mode](../guide/graphql_mode.md) — The GraphQL API used under the hood by MCP
