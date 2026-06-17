"""Tests that Resolver handles deep trees without RecursionError.

The recursive ``_process_level`` implementation (pre-refactor) crashes when the
tree depth approaches ``sys.getrecursionlimit()`` because each BFS level adds a
Python frame. The Phase A + Phase B iterative refactor removes this limit.

See issue #77 item C1.
"""
from __future__ import annotations

import sys

import pytest
from pydantic import BaseModel

from nexusx.resolver import Resolver


def _build_chain(depth: int) -> BaseModel:
    """Build a chain of nested ``list[Node]`` containers of given depth.

    Uses a self-referencing ``Node`` type so all levels share one class. Each
    level has exactly one child, producing a chain rather than a fan-out tree
    — every level forces a new BFS recursion frame in the old implementation.
    """
    class Node(BaseModel):
        id: int
        children: list[Node] = []
        label: str = ""

        def post_label(self):
            return f"n-{self.id}"

    Node.model_rebuild()

    # id=1 is the leaf (empty children). Each successive wrap adds one level.
    node: Node = Node(id=1)
    for i in range(2, depth + 1):
        node = Node(id=i, children=[node])
    return node


@pytest.mark.usefixtures("test_db")
async def test_deep_chain_no_recursion_error():
    """A tree deeper than ``sys.getrecursionlimit()`` must resolve without
    ``RecursionError``. Pre-refactor: fails around depth=1000. Post-refactor:
    iterative, no recursion limit.
    """
    depth = sys.getrecursionlimit() + 200
    root = _build_chain(depth)

    result = await Resolver().resolve(root)

    # Walk down the only-child chain and verify post_label ran at every level.
    cur = result
    levels_visited = 0
    while cur is not None:
        levels_visited += 1
        assert cur.label == f"n-{cur.id}", (
            f"At level {levels_visited}: expected label n-{cur.id}, got {cur.label}"
        )
        kids = getattr(cur, "children", None)
        if kids:
            cur = kids[0]
        else:
            cur = None

    assert levels_visited == depth, (
        f"Walked {levels_visited} levels, expected {depth}"
    )


@pytest.mark.usefixtures("test_db")
async def test_deep_chain_correctness():
    """At moderate depth (50), verify the chain resolves with correct values
    at every level — guards against the iterative refactor dropping nodes."""
    depth = 50
    root = _build_chain(depth)

    result = await Resolver().resolve(root)

    cur = result
    expected_id = depth
    while cur is not None:
        assert cur.id == expected_id
        assert cur.label == f"n-{expected_id}"
        kids = getattr(cur, "children", None)
        if kids:
            cur = kids[0]
            expected_id -= 1
        else:
            # Leaf reached — id should be 1
            assert cur.id == 1
            break
