"""Tests for create_jsonrpc_router — JSON-RPC 2.0 endpoint for UseCaseService."""

from __future__ import annotations

from typing import Annotated

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from nexusx.decorator import mutation, query
from nexusx.use_case.business import UseCaseService
from nexusx.use_case.context import FromContext
from nexusx.use_case.jsonrpc import create_jsonrpc_router
from nexusx.use_case.types import UseCaseAppConfig

# ──────────────────────────────────────────────────
# Test DTOs
# ──────────────────────────────────────────────────


class UserDTO(BaseModel):
    id: int
    name: str


# ──────────────────────────────────────────────────
# Test Services
# ──────────────────────────────────────────────────


class UserService(UseCaseService):
    """User management service."""

    @query
    async def list_users(cls) -> list[UserDTO]:
        """Get all users."""
        return [UserDTO(id=1, name="Alice"), UserDTO(id=2, name="Bob")]

    @query
    async def get_user(cls, user_id: int) -> UserDTO | None:
        """Get a user by ID."""
        if user_id == 1:
            return UserDTO(id=1, name="Alice")
        return None

    @mutation
    async def create_user(cls, name: str, email: str) -> UserDTO:
        """Create a new user."""
        return UserDTO(id=99, name=name)


class PingService(UseCaseService):
    """Ping service."""

    @query
    async def ping(cls) -> str:
        """Return pong."""
        return "pong"


class ContextService(UseCaseService):
    """Service using FromContext."""

    @query
    async def whoami(cls, user_id: Annotated[int, FromContext()]) -> UserDTO:
        return UserDTO(id=user_id, name="from_context")

    @query
    async def greet(
        cls,
        user_id: Annotated[int, FromContext()],
        message: str,
    ) -> str:
        return f"user={user_id},msg={message}"


# ──────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────


def _extract_user(request):
    return {"user_id": int(request.headers.get("X-User-Id", "0"))}


def _make_app(config: UseCaseAppConfig, **kwargs) -> TestClient:
    app = FastAPI()
    router = create_jsonrpc_router(config, **kwargs)
    app.include_router(router)
    return TestClient(app)


def _rpc(method: str, params: dict | None = None, req_id: int | None = 1) -> dict:
    return {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": req_id}


# ──────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────


@pytest.fixture
def client():
    return _make_app(
        UseCaseAppConfig(name="test", services=[UserService, PingService]),
    )


@pytest.fixture
def no_mutation_client():
    return _make_app(
        UseCaseAppConfig(name="test", services=[UserService], enable_mutation=False),
    )


@pytest.fixture
def context_client():
    return _make_app(
        UseCaseAppConfig(
            name="test",
            services=[ContextService],
            context_extractor=_extract_user,
        ),
    )


# ──────────────────────────────────────────────────
# Tests: Basic invocation
# ──────────────────────────────────────────────────


class TestBasicInvocation:
    def test_no_params_method(self, client):
        resp = client.post("/rpc", json=_rpc("UserService.list_users"))
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == 1
        assert len(body["result"]) == 2
        assert body["result"][0]["name"] == "Alice"

    def test_with_params_method(self, client):
        resp = client.post("/rpc", json=_rpc("UserService.get_user", {"user_id": 1}))
        assert resp.status_code == 200
        assert resp.json()["result"]["name"] == "Alice"

    def test_returns_none(self, client):
        resp = client.post("/rpc", json=_rpc("UserService.get_user", {"user_id": 999}))
        assert resp.status_code == 200
        assert resp.json()["result"] is None

    def test_mutation_method(self, client):
        resp = client.post(
            "/rpc",
            json=_rpc("UserService.create_user", {"name": "Charlie", "email": "c@t.com"}),
        )
        assert resp.status_code == 200
        assert resp.json()["result"]["name"] == "Charlie"

    def test_ping(self, client):
        resp = client.post("/rpc", json=_rpc("PingService.ping"))
        assert resp.status_code == 200
        assert resp.json()["result"] == "pong"

    def test_empty_params(self, client):
        resp = client.post("/rpc", json={"jsonrpc": "2.0", "method": "PingService.ping", "id": 1})
        assert resp.status_code == 200
        assert resp.json()["result"] == "pong"


# ──────────────────────────────────────────────────
# Tests: Error handling
# ──────────────────────────────────────────────────


class TestErrors:
    def test_method_not_found_service(self, client):
        resp = client.post("/rpc", json=_rpc("UnknownService.method"))
        assert resp.json()["error"]["code"] == -32601

    def test_method_not_found_method(self, client):
        resp = client.post("/rpc", json=_rpc("UserService.unknown_method"))
        assert resp.json()["error"]["code"] == -32601

    def test_invalid_method_format_no_dot(self, client):
        resp = client.post("/rpc", json=_rpc("list_users"))
        assert resp.json()["error"]["code"] == -32601

    def test_invalid_params_missing_required(self, client):
        resp = client.post("/rpc", json=_rpc("UserService.get_user", {}))
        assert resp.json()["error"]["code"] == -32602

    def test_invalid_jsonrpc_version(self, client):
        resp = client.post(
            "/rpc",
            json={"jsonrpc": "1.0", "method": "UserService.list_users", "id": 1},
        )
        assert resp.json()["error"]["code"] == -32600

    def test_missing_jsonrpc_field(self, client):
        resp = client.post("/rpc", json={"method": "UserService.list_users", "id": 1})
        assert resp.json()["error"]["code"] == -32600

    def test_missing_method_field(self, client):
        resp = client.post("/rpc", json={"jsonrpc": "2.0", "id": 1})
        assert resp.json()["error"]["code"] == -32600

    def test_empty_method(self, client):
        resp = client.post("/rpc", json={"jsonrpc": "2.0", "method": "", "id": 1})
        assert resp.json()["error"]["code"] == -32600

    def test_params_not_dict(self, client):
        resp = client.post(
            "/rpc",
            json={"jsonrpc": "2.0", "method": "UserService.list_users", "params": [1, 2], "id": 1},
        )
        assert resp.json()["error"]["code"] == -32602

    def test_mutation_disabled(self, no_mutation_client):
        resp = no_mutation_client.post(
            "/rpc",
            json=_rpc("UserService.create_user", {"name": "X", "email": "x@t.com"}),
        )
        assert resp.json()["error"]["code"] == -32601

    def test_error_preserves_id(self, client):
        resp = client.post("/rpc", json=_rpc("UnknownService.method", req_id=42))
        assert resp.json()["id"] == 42

    def test_error_id_is_none_when_no_id(self, client):
        resp = client.post("/rpc", json={"jsonrpc": "2.0", "method": "UnknownService.method"})
        assert resp.json()["id"] is None


# ──────────────────────────────────────────────────
# Tests: Batch requests
# ──────────────────────────────────────────────────


class TestBatch:
    def test_batch_multiple_requests(self, client):
        batch = [
            _rpc("UserService.list_users", req_id=1),
            _rpc("PingService.ping", req_id=2),
        ]
        resp = client.post("/rpc", json=batch)
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 2
        by_id = {r["id"]: r for r in results}
        assert len(by_id[1]["result"]) == 2
        assert by_id[2]["result"] == "pong"

    def test_batch_with_error(self, client):
        batch = [
            _rpc("UserService.list_users", req_id=1),
            _rpc("UnknownService.method", req_id=2),
        ]
        resp = client.post("/rpc", json=batch)
        results = resp.json()
        assert len(results) == 2
        by_id = {r["id"]: r for r in results}
        assert "result" in by_id[1]
        assert "error" in by_id[2]

    def test_empty_batch(self, client):
        resp = client.post("/rpc", json=[])
        assert resp.json()["error"]["code"] == -32600

    def test_body_not_dict_or_list(self, client):
        resp = client.post("/rpc", json="hello")
        assert resp.json()["error"]["code"] == -32600


# ──────────────────────────────────────────
# Tests: FromContext injection
# ──────────────────────────────────────────


class TestFromContext:
    def test_context_injected(self, context_client):
        resp = context_client.post(
            "/rpc", json=_rpc("ContextService.whoami"), headers={"X-User-Id": "42"},
        )
        assert resp.json()["result"]["id"] == 42

    def test_context_with_body_param(self, context_client):
        resp = context_client.post(
            "/rpc",
            json=_rpc("ContextService.greet", {"message": "hello"}),
            headers={"X-User-Id": "7"},
        )
        assert resp.json()["result"] == "user=7,msg=hello"

    def test_context_default(self, context_client):
        resp = context_client.post("/rpc", json=_rpc("ContextService.whoami"))
        assert resp.json()["result"]["id"] == 0


# ──────────────────────────────────────────────────
# Tests: Router configuration
# ──────────────────────────────────────────────────


class TestRouterConfig:
    def test_returns_api_router(self):
        from fastapi import APIRouter

        router = create_jsonrpc_router(UseCaseAppConfig(name="test", services=[UserService]))
        assert isinstance(router, APIRouter)

    def test_custom_path(self):
        app = FastAPI()
        router = create_jsonrpc_router(
            UseCaseAppConfig(name="test", services=[UserService]), path="/api/rpc",
        )
        app.include_router(router)
        client = TestClient(app)
        resp = client.post("/api/rpc", json=_rpc("UserService.list_users"))
        assert resp.status_code == 200

    def test_context_extractor_override(self):
        """Router-level context_extractor overrides config-level."""
        app = FastAPI()
        router = create_jsonrpc_router(
            UseCaseAppConfig(name="test", services=[ContextService]),
            context_extractor=lambda r: {"user_id": 999},
        )
        app.include_router(router)
        client = TestClient(app)
        resp = client.post("/rpc", json=_rpc("ContextService.whoami"))
        assert resp.json()["result"]["id"] == 999
