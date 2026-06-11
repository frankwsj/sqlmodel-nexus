"""GraphQL QueryExecutor benchmarks.

Scenarios:
  Q1: 1-level — tasks → owner
  Q2: 2-level — sprints → tasks → owner
  Q3: wide — users → posts + comments (parallel siblings)
  Q4: deep+wide — users → posts → comments + comments → post

Usage:
    uv run pytest benchmarks/test_02_graphql.py --benchmark-only
"""

import asyncio

from sqlmodel import select

from nexusx.execution.query_executor import QueryExecutor
from nexusx.loader.registry import ErManager
from nexusx.query_parser import QueryParser

from benchmarks.conftest import (
    BLOG_ENTITIES,
    SPRINT_ENTITIES,
    Comment,
    Post,
    Sprint,
    Task,
    User,
)


def _sync(coro):
    return asyncio.run(coro)


def _make_query_method(entity_cls, session_factory):
    async def get_all():
        async with session_factory() as session:
            return list((await session.exec(select(entity_cls))).all())

    return get_all


def _make_executor(entities, session_factory):
    registry = ErManager(entities=entities, session_factory=session_factory)
    return QueryExecutor(registry)


def _run_query(executor, gql, parsed, query_methods, entities):
    return executor.execute_query(gql, None, None, parsed, query_methods, {}, entities)


# ──────────────────────────────────────────────────────────
# Q1: 1-level — tasks → owner
# ──────────────────────────────────────────────────────────


def test_q1_one_level(benchmark, sprint_db):
    _sync(sprint_db.ensure())

    executor = _make_executor(SPRINT_ENTITIES, sprint_db.sf)
    method = _make_query_method(Task, sprint_db.sf)
    query_methods = {"tasks": (Task, method)}
    gql = "{ tasks { id title owner { id name } } }"
    parsed = QueryParser().parse(gql)

    async def _run():
        return await _run_query(executor, gql, parsed, query_methods, SPRINT_ENTITIES)

    benchmark(lambda: _sync(_run()))


# ──────────────────────────────────────────────────────────
# Q2: 2-level — sprints → tasks → owner
# ──────────────────────────────────────────────────────────


def test_q2_two_level(benchmark, sprint_db):
    _sync(sprint_db.ensure())

    executor = _make_executor(SPRINT_ENTITIES, sprint_db.sf)
    method = _make_query_method(Sprint, sprint_db.sf)
    query_methods = {"sprints": (Sprint, method)}
    gql = "{ sprints { id name tasks { id title owner { id name } } } }"
    parsed = QueryParser().parse(gql)

    async def _run():
        return await _run_query(executor, gql, parsed, query_methods, SPRINT_ENTITIES)

    benchmark(lambda: _sync(_run()))


# ──────────────────────────────────────────────────────────
# Q3: wide — users → posts + comments
# ──────────────────────────────────────────────────────────


def test_q3_wide(benchmark, blog_db):
    _sync(blog_db.ensure())

    executor = _make_executor(BLOG_ENTITIES, blog_db.sf)
    method = _make_query_method(User, blog_db.sf)
    query_methods = {"users": (User, method)}
    gql = "{ users { id name posts { id title } comments { id content } } }"
    parsed = QueryParser().parse(gql)

    async def _run():
        return await _run_query(executor, gql, parsed, query_methods, BLOG_ENTITIES)

    benchmark(lambda: _sync(_run()))


# ──────────────────────────────────────────────────────────
# Q4: deep+wide — users → posts → comments + comments → post
# ──────────────────────────────────────────────────────────


def test_q4_deep_wide(benchmark, blog_db):
    _sync(blog_db.ensure())

    executor = _make_executor(BLOG_ENTITIES, blog_db.sf)
    method = _make_query_method(User, blog_db.sf)
    query_methods = {"users": (User, method)}
    gql = (
        "{ users { id name posts { id title comments { id content } } "
        "comments { id content post { id title } } } }"
    )
    parsed = QueryParser().parse(gql)

    async def _run():
        return await _run_query(executor, gql, parsed, query_methods, BLOG_ENTITIES)

    benchmark(lambda: _sync(_run()))
