"""Core API (DefineSubset + Resolver) benchmarks.

Scenarios:
  L1: Pure field selection — UserSummary (no relationships)
  L2: Single-level relationship — TaskSummary → owner (auto-loaded)
  L3: Two-level relationships + derived fields — SprintSummary → tasks → owner
  L4: Cross-layer data flow — ExposeAs + SendTo + Collector

Usage:
    uv run pytest benchmarks/test_01_resolver.py --benchmark-only
"""

import asyncio

from benchmarks.conftest import (
    SprintDetail,
    SprintSummary,
    TaskSummary,
    UserSummary,
    build_dto_select,
)


def _sync(coro):
    return asyncio.run(coro)


# ──────────────────────────────────────────────────────────
# L1: Pure field selection
# ──────────────────────────────────────────────────────────


def test_l1_field_selection(benchmark, sprint_db):
    _sync(sprint_db.ensure(n_users=100, n_sprints=5, n_tasks_per_sprint=5))

    async def _run():
        stmt = build_dto_select(UserSummary)
        async with sprint_db.sf() as session:
            rows = (await session.exec(stmt)).all()
        return [UserSummary(**dict(row._mapping)) for row in rows]

    benchmark(lambda: _sync(_run()))


# ──────────────────────────────────────────────────────────
# L2: Single-level relationship (TaskSummary → owner)
# ──────────────────────────────────────────────────────────


def test_l2_one_level_relation(benchmark, sprint_db):
    _sync(sprint_db.ensure())

    async def _run():
        stmt = build_dto_select(TaskSummary)
        async with sprint_db.sf() as session:
            rows = (await session.exec(stmt)).all()
        dtos = [TaskSummary(**dict(row._mapping)) for row in rows]
        return await sprint_db.resolver().resolve(dtos)

    benchmark(lambda: _sync(_run()))


# ──────────────────────────────────────────────────────────
# L3: Two-level + derived fields (SprintSummary)
# ──────────────────────────────────────────────────────────


def test_l3_two_level_derived(benchmark, sprint_db):
    _sync(sprint_db.ensure())

    async def _run():
        stmt = build_dto_select(SprintSummary)
        async with sprint_db.sf() as session:
            rows = (await session.exec(stmt)).all()
        dtos = [SprintSummary(**dict(row._mapping)) for row in rows]
        return await sprint_db.resolver().resolve(dtos)

    benchmark(lambda: _sync(_run()))


# ──────────────────────────────────────────────────────────
# L4: Cross-layer data flow (SprintDetail)
# ──────────────────────────────────────────────────────────


def test_l4_cross_layer(benchmark, sprint_db):
    _sync(sprint_db.ensure())

    async def _run():
        stmt = build_dto_select(SprintDetail)
        async with sprint_db.sf() as session:
            rows = (await session.exec(stmt)).all()
        dtos = [SprintDetail(**dict(row._mapping)) for row in rows]
        return await sprint_db.resolver().resolve(dtos)

    benchmark(lambda: _sync(_run()))


# ──────────────────────────────────────────────────────────
# Large dataset
# ──────────────────────────────────────────────────────────


def test_l3_large_dataset(benchmark, sprint_db):
    _sync(sprint_db.ensure(n_users=50, n_sprints=20, n_tasks_per_sprint=50))

    async def _run():
        stmt = build_dto_select(SprintSummary)
        async with sprint_db.sf() as session:
            rows = (await session.exec(stmt)).all()
        dtos = [SprintSummary(**dict(row._mapping)) for row in rows]
        return await sprint_db.resolver().resolve(dtos)

    benchmark(lambda: _sync(_run()))
