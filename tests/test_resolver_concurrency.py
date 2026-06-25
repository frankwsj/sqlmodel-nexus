"""Tests for Resolver instance state isolation — concurrent resolve() guard.

Migrated from pydantic-resolve #289: a Resolver holds per-call mutable state
on self (_node_collectors, _loader_cache, the levels list inside _traverse).
Two overlapping resolve() calls on the same instance clobber each other and
surface as a cryptic KeyError. The fix is a _in_resolve flag + try/finally
that raises a clear RuntimeError instead.

Run::

    pytest tests/test_resolver_concurrency.py -v
"""
from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from nexusx.resolver import Resolver

# ──────────────────────────────────────────────────────────
# Test: same Resolver instance shared across concurrent resolve() calls
# ──────────────────────────────────────────────────────────


class _SlowModel(BaseModel):
    name: str
    greeting: str = ""

    async def resolve_greeting(self):
        # Yield to the event loop so a second resolve() can interleave
        # while this one is mid-flight.
        await asyncio.sleep(0.01)
        return f"Hello, {self.name}!"


class TestResolverConcurrentGuard:
    async def test_concurrent_resolve_on_same_instance_raises(self):
        """Two overlapping resolve() calls on the same Resolver must raise
        a clear RuntimeError instead of silently corrupting state."""
        resolver = Resolver()

        async def _go(name: str) -> str:
            model = _SlowModel(name=name)
            result = await resolver.resolve(model)
            return result.greeting

        with pytest.raises(RuntimeError, match="already running"):
            await asyncio.gather(_go("Alice"), _go("Bob"))

    async def test_sequential_resolve_on_same_instance_ok(self):
        """Sequential (non-overlapping) resolve() calls on the same Resolver
        are fine — the guard resets between calls via try/finally."""
        resolver = Resolver()

        m1 = _SlowModel(name="Alice")
        r1 = await resolver.resolve(m1)
        assert r1.greeting == "Hello, Alice!"

        # If _in_resolve weren't reset in finally, this would raise.
        m2 = _SlowModel(name="Bob")
        r2 = await resolver.resolve(m2)
        assert r2.greeting == "Hello, Bob!"

    async def test_guard_resets_after_exception(self):
        """If resolve() raises, the guard must still reset — otherwise the
        Resolver would be permanently stuck in _in_resolve=True."""
        resolver = Resolver()

        class _Boom(BaseModel):
            name: str
            value: str = ""

            def resolve_value(self):
                raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await resolver.resolve(_Boom(name="x"))

        # Reusing the resolver must work — the RuntimeError guard would fire
        # here if _in_resolve weren't reset in finally.
        m = _SlowModel(name="after")
        r = await resolver.resolve(m)
        assert r.greeting == "Hello, after!"

    async def test_separate_instances_concurrent_ok(self):
        """Concurrent resolve() on separate Resolver instances is fine —
        only sharing the SAME instance across calls is forbidden."""
        async def _go(name: str) -> str:
            resolver = Resolver()
            model = _SlowModel(name=name)
            result = await resolver.resolve(model)
            return result.greeting

        results = await asyncio.gather(_go("Alice"), _go("Bob"))
        assert sorted(results) == ["Hello, Alice!", "Hello, Bob!"]
