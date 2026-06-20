"""UseCase module — UseCase GraphQL MCP + legacy MCP / FastAPI / Voyager entry points.

Public API:
- UseCase GraphQL MCP (3.0+): ``create_use_case_graphql_mcp_server``, plus
  direct schema access via ``build_compose_schema`` / ``ComposeSchema`` /
  ``ComposeSchemaError``.
- FastAPI / JSON-RPC / Voyager: ``create_router``, ``create_jsonrpc_router``.
"""

from nexusx.use_case.business import UseCaseService, get_return_type
from nexusx.use_case.cli import create_use_case_cli
from nexusx.use_case.compose_mcp_server import create_use_case_graphql_mcp_server
from nexusx.use_case.compose_schema import (
    ComposeSchema,
    ComposeSchemaError,
    build_compose_schema,
)
from nexusx.use_case.context import FromContext
from nexusx.use_case.flat_server import create_use_case_flat_server
from nexusx.use_case.jsonrpc import create_jsonrpc_router
from nexusx.use_case.router import create_router
from nexusx.use_case.selection import SelectionError
from nexusx.use_case.server import create_use_case_mcp_server
from nexusx.use_case.types import UseCaseAppConfig

__all__ = [
    # UseCase GraphQL MCP (3.0+)
    "create_use_case_graphql_mcp_server",
    "build_compose_schema",
    "ComposeSchema",
    "ComposeSchemaError",
    # Legacy direct-call MCP (scheduled for removal — see spec FR-010)
    "create_use_case_mcp_server",
    "create_use_case_flat_server",
    # Orthogonal surfaces
    "create_use_case_cli",
    "create_jsonrpc_router",
    "create_router",
    # Service / config / annotations
    "UseCaseService",
    "UseCaseAppConfig",
    "FromContext",
    "SelectionError",
    "get_return_type",
]
