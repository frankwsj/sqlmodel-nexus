# MCP API Reference

Create MCP services for AI agent integration with GraphQL-based tools.

## create_simple_mcp_server

Create a single-app MCP service with GraphQL-based tools.

```python
from nexusx.mcp import create_simple_mcp_server

mcp = create_simple_mcp_server(
    base=SQLModel,              # SQLModel base class
    name="My API",              # Service name
    session_factory=async_session,  # Session factory
)
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `base` | `type` | Yes | SQLModel base class |
| `name` | `str` | Yes | Service name |
| `session_factory` | `Callable` | No | Session factory |

!!! tip
    Use the simple server when you have a single application or are just getting started with MCP integration. It provides a straightforward interface with three core tools: schema inspection, query execution, and mutation execution.

### Generated Tools

| Tool | Description |
|------|-------------|
| `get_schema()` | Get GraphQL schema |
| `graphql_query(query)` | Execute GraphQL query |
| `graphql_mutation(mutation)` | Execute GraphQL mutation |

## create_mcp_server

Create a multi-app MCP service that manages multiple applications.

```python
from nexusx.mcp import create_mcp_server

mcp = create_mcp_server(
    apps=[
        {"name": "blog", "base": BlogBase, "description": "Blog API"},
        {"name": "shop", "base": ShopBase, "description": "Shop API"},
    ],
    name="Multi-App API",
)
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `apps` | `list[dict]` | Yes | Application configuration list |
| `name` | `str` | Yes | Service name |

!!! tip
    Use the multi-app server when you have multiple distinct domains or bounded contexts (like a blog API and a shop API) that you want to expose as separate apps. This keeps tools organized and allows agents to discover and query each domain independently.

### Generated Tools

| Tool | Description |
|------|-------------|
| `list_apps()` | List all applications |
| `list_queries(app_name)` | List queries for an app |
| `get_query_schema(name, app_name)` | Get query schema |
| `graphql_query(query, app_name)` | Execute query |

## AppConfig

Multi-app configuration type that defines each application's structure.

The `apps` parameter in `create_mcp_server` accepts a list of dictionaries with these fields:

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Application name |
| `base` | `type` | SQLModel base class |
| `description` | `str` | Application description |
| `session_factory` | `Callable` | Session factory |
