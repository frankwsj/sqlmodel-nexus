"""Tests for cross-layer data flow: ExposeAs, SendTo, Collector."""

from __future__ import annotations

from typing import Annotated

import pytest
from pydantic import BaseModel

from nexusx.context import Collector, ExposeAs, ICollector, SendTo
from nexusx.resolver import Loader, Resolver

# ──────────────────────────────────────────────────────────
# Test: ExposeAs — ancestor context passing
# ──────────────────────────────────────────────────────────

class TestExposeAs:
    async def test_basic_expose_to_descendant(self):
        """ExposeAs field should be available in descendant ancestor_context."""

        class Child(BaseModel):
            name: str
            parent_greeting: str = ""

            def post_parent_greeting(self, ancestor_context=None):
                if ancestor_context is None:
                    ancestor_context = {}
                return ancestor_context.get("greeting", "no greeting")

        class Parent(BaseModel):
            greeting: Annotated[str, ExposeAs("greeting")]
            children: list[Child] = []

        parent = Parent(
            greeting="Hello from parent",
            children=[Child(name="A"), Child(name="B")],
        )
        result = await Resolver().resolve(parent)

        assert result.children[0].parent_greeting == "Hello from parent"
        assert result.children[1].parent_greeting == "Hello from parent"

    async def test_multi_level_expose(self):
        """ExposeAs should propagate through multiple levels."""

        class GrandChild(BaseModel):
            name: str
            root_name: str = ""

            def post_root_name(self, ancestor_context=None):
                if ancestor_context is None:
                    ancestor_context = {}
                return ancestor_context.get("root_name", "unknown")

        class Child(BaseModel):
            name: str
            children: list[GrandChild] = []

        class Root(BaseModel):
            name: Annotated[str, ExposeAs("root_name")]
            children: list[Child] = []

        root = Root(
            name="RootNode",
            children=[
                Child(name="Child1", children=[GrandChild(name="GC1")]),
                Child(name="Child2", children=[GrandChild(name="GC2")]),
            ],
        )
        result = await Resolver().resolve(root)

        assert result.children[0].children[0].root_name == "RootNode"
        assert result.children[1].children[0].root_name == "RootNode"

    async def test_expose_with_resolve(self):
        """ExposeAs should work alongside resolve_* methods."""

        class Child(BaseModel):
            name: str
            full_label: str = ""

            def resolve_name(self):
                return f"child_{self.name}"

            def post_full_label(self, ancestor_context=None):
                if ancestor_context is None:
                    ancestor_context = {}
                prefix = ancestor_context.get("prefix", "")
                return f"{prefix}/{self.name}"

        class Parent(BaseModel):
            prefix: Annotated[str, ExposeAs("prefix")]
            children: list[Child] = []

        parent = Parent(
            prefix="P",
            children=[Child(name="A"), Child(name="B")],
        )
        result = await Resolver().resolve(parent)

        # resolve_name changes name, post uses it
        assert result.children[0].full_label == "P/child_A"
        assert result.children[1].full_label == "P/child_B"

    async def test_expose_multiple_fields(self):
        """Multiple ExposeAs fields on one node."""

        class Child(BaseModel):
            info: str = ""

            def post_info(self, ancestor_context=None):
                if ancestor_context is None:
                    ancestor_context = {}
                return f"{ancestor_context.get('a', '')}-{ancestor_context.get('b', '')}"

        class Parent(BaseModel):
            field_a: Annotated[str, ExposeAs("a")]
            field_b: Annotated[str, ExposeAs("b")]
            children: list[Child] = []

        parent = Parent(field_a="A", field_b="B", children=[Child()])
        result = await Resolver().resolve(parent)

        assert result.children[0].info == "A-B"


# ──────────────────────────────────────────────────────────
# Test: SendTo + Collector — upward aggregation
# ──────────────────────────────────────────────────────────

class TestSendToCollector:
    async def test_basic_collector(self):
        """Collector should aggregate values from SendTo-annotated fields."""

        class Child(BaseModel):
            name: Annotated[str, SendTo("names")]

        class Parent(BaseModel):
            children: list[Child] = []
            collected_names: list[str] = []

            def post_collected_names(self, collector=Collector("names")):
                return collector.values()

        parent = Parent(
            children=[Child(name="Alice"), Child(name="Bob"), Child(name="Charlie")]
        )
        result = await Resolver().resolve(parent)

        assert "Alice" in result.collected_names
        assert "Bob" in result.collected_names
        assert "Charlie" in result.collected_names

    async def test_collector_flat_mode(self):
        """Collector with flat=True should flatten list values."""

        class Child(BaseModel):
            tags: Annotated[list[str], SendTo("all_tags")] = []

        class Parent(BaseModel):
            children: list[Child] = []
            all_tags: list[str] = []

            def post_all_tags(self, collector=Collector("all_tags", flat=True)):
                return collector.values()

        parent = Parent(
            children=[
                Child(tags=["a", "b"]),
                Child(tags=["c", "d"]),
            ]
        )
        result = await Resolver().resolve(parent)

        assert result.all_tags == ["a", "b", "c", "d"]

    async def test_collector_with_resolve(self):
        """Collector should work with resolve_* — collected after resolve."""

        class Child(BaseModel):
            name: str = ""
            resolved_name: Annotated[str, SendTo("resolved")] = ""

            def resolve_resolved_name(self):
                return f"resolved_{self.name}"

        class Parent(BaseModel):
            children: list[Child] = []
            resolved_names: list[str] = []

            def post_resolved_names(self, collector=Collector("resolved")):
                return collector.values()

        parent = Parent(
            children=[
                Child(name="Alice"),
                Child(name="Bob"),
            ]
        )
        result = await Resolver().resolve(parent)

        # resolve_resolved_name runs first, sets the field
        # then _add_values_into_collectors reads the resolved value
        assert result.children[0].resolved_name == "resolved_Alice"
        assert "resolved_Alice" in result.resolved_names
        assert "resolved_Bob" in result.resolved_names

    async def test_collector_none_value_skipped(self):
        """SendTo fields with None value should not be collected."""

        class Child(BaseModel):
            name: str
            optional_val: Annotated[str | None, SendTo("vals")] = None

        class Parent(BaseModel):
            children: list[Child] = []
            values: list[str] = []

            def post_values(self, collector=Collector("vals")):
                return collector.values()

        parent = Parent(
            children=[
                Child(name="A", optional_val="yes"),
                Child(name="B"),  # None default
                Child(name="C", optional_val="yes2"),
            ]
        )
        result = await Resolver().resolve(parent)

        assert result.values == ["yes", "yes2"]


# ──────────────────────────────────────────────────────────
# Test: ExposeAs + SendTo + Collector combined
# ──────────────────────────────────────────────────────────

class TestCombinedContext:
    async def test_full_cross_layer_flow(self):
        """Full scenario: parent exposes context → child uses it and sends data back."""

        class TaskItem(BaseModel):
            title: str
            full_title: str = ""
            completed: Annotated[bool, SendTo("completed_tasks")] = False

            def post_full_title(self, ancestor_context=None):
                if ancestor_context is None:
                    ancestor_context = {}
                sprint_name = ancestor_context.get("sprint_name", "unknown")
                return f"{sprint_name} / {self.title}"

        class SprintItem(BaseModel):
            name: Annotated[str, ExposeAs("sprint_name")]
            tasks: list[TaskItem] = []
            completed_titles: list[str] = []

            def post_completed_titles(self, collector=Collector("completed_tasks")):
                return collector.values()

        sprint = SprintItem(
            name="Sprint 1",
            tasks=[
                TaskItem(title="Task A", completed=True),
                TaskItem(title="Task B", completed=False),
                TaskItem(title="Task C", completed=True),
            ],
        )
        result = await Resolver().resolve(sprint)

        # ExposeAs: children see sprint_name
        assert result.tasks[0].full_title == "Sprint 1 / Task A"
        assert result.tasks[1].full_title == "Sprint 1 / Task B"

        # SendTo + Collector: parent collects completed task values
        assert result.completed_titles == [True, False, True]

    async def test_expose_and_collector_on_resolve_fields(self):
        """ExposeAs and Collector work with DataLoader-resolved fields."""

        class ChildDTO(BaseModel):
            name: str = ""
            label: str = ""

            def resolve_name(self):
                return "resolved_child"

            def post_label(self, ancestor_context=None):
                if ancestor_context is None:
                    ancestor_context = {}
                prefix = ancestor_context.get("prefix", "?")
                return f"{prefix}:{self.name}"

        class ParentDTO(BaseModel):
            prefix: Annotated[str, ExposeAs("prefix")]
            children: list[ChildDTO] = []

        parent = ParentDTO(
            prefix="P",
            children=[ChildDTO(), ChildDTO()],
        )
        result = await Resolver().resolve(parent)

        assert result.children[0].label == "P:resolved_child"
        assert result.children[1].label == "P:resolved_child"


# ──────────────────────────────────────────────────────────
# Test: BFS edge cases — SendTo multi-collector
# ──────────────────────────────────────────────────────────


class TestSendToMultiCollector:
    async def test_send_to_multiple_collectors(self):
        """One field can send to multiple Collectors via SendTo tuple."""

        class Child(BaseModel):
            name: Annotated[str, SendTo(("names", "all_names"))]

        class Parent(BaseModel):
            children: list[Child] = []
            names: list[str] = []
            all_names: list[str] = []

            def post_names(self, collector=Collector("names")):
                return collector.values()

            def post_all_names(self, collector=Collector("all_names")):
                return collector.values()

        parent = Parent(children=[Child(name="Alice"), Child(name="Bob")])
        result = await Resolver().resolve(parent)

        assert "Alice" in result.names
        assert "Bob" in result.names
        assert "Alice" in result.all_names
        assert "Bob" in result.all_names


# ──────────────────────────────────────────────────────────
# Test: Auto-load + SendTo — verify no duplication
# ──────────────────────────────────────────────────────────


class TestAutoLoadSendTo:
    @pytest.mark.usefixtures("test_db")
    async def test_autoload_no_sendto_duplication(self):
        """Auto-loaded children should not be traversed twice (SendTo values)."""
        from sqlmodel import select

        from nexusx.loader.registry import ErManager
        from nexusx.subset import DefineSubset
        from tests.conftest import (
            FixtureSprint,
            FixtureTask,
            FixtureUser,
            get_test_session_factory,
        )

        session_factory = get_test_session_factory()
        registry = ErManager(
            entities=[FixtureUser, FixtureSprint, FixtureTask],
            session_factory=session_factory,
        )

        class UserDTO(DefineSubset):
            __subset__ = (FixtureUser, ("id", "name"))

        class TaskDTO(DefineSubset):
            __subset__ = (FixtureTask, ("id", "title", "owner_id"))
            owner: UserDTO | None = None
            title_value: Annotated[str, SendTo("titles")] = ""

            def post_title_value(self):
                return self.title

        class SprintDTO(DefineSubset):
            __subset__ = (FixtureSprint, ("id", "name"))
            tasks: list[TaskDTO] = []
            titles: list[str] = []

            def post_titles(self, collector=Collector("titles")):
                return collector.values()

        async with session_factory() as session:
            sprints = (await session.exec(select(FixtureSprint))).all()

        dtos = [SprintDTO(id=s.id, name=s.name) for s in sprints]
        result = await Resolver(registry).resolve(dtos)

        # Each sprint has exactly 2 tasks — titles should appear once each
        assert len(result[0].titles) == 2
        assert len(result[1].titles) == 2


# ──────────────────────────────────────────────────────────
# Test: Level-by-level collection — ancestor also collects
# ──────────────────────────────────────────────────────────


class TestCollectorLevelByLevel:
    async def test_level_collection(self):
        """BFS: Collector at parent only collects from its direct children's SendTo.

        In BFS mode, post_* at level N runs before level N+1 is processed.
        So A's Collector only gets values from B (direct children), not from C (grandchildren).
        B's Collector gets values from C because C is processed in B's child level.
        """

        class C(BaseModel):
            name: Annotated[str, SendTo("c_name")]

        class B(BaseModel):
            children: list[C]
            names: list[str] = []

            def post_names(self, collector=Collector("c_name")):
                return collector.values()

        class A(BaseModel):
            children: list[B]
            names: list[str] = []

            def post_names(self, collector=Collector("c_name")):
                return collector.values()

        tree = A(
            children=[
                B(children=[C(name="c1"), C(name="c2")]),
                B(children=[C(name="c3"), C(name="c4")]),
            ]
        )
        result = await Resolver().resolve(tree)

        # B[0] collects from its direct C children
        assert result.children[0].names == ["c1", "c2"]
        # B[1] collects from its direct C children
        assert result.children[1].names == ["c3", "c4"]
        # A's Collector is empty: A's post_* runs before B/C are processed
        assert result.names == []


# ──────────────────────────────────────────────────────────
# Test: Multiple sources (different levels) → same collector
# ──────────────────────────────────────────────────────────


class TestMultipleCollectSource:
    async def test_collect_from_multiple_levels(self):
        """BFS: Collector at parent collects from ALL descendants.

        The Resolver propagates collector snapshots through the tree,
        so A's Collector aggregates values from both B and C nodes.
        """

        class C(BaseModel):
            name: Annotated[str, SendTo("field_name")] = ""

            async def post_name(self):
                return f"{self.name}!"

        class B(BaseModel):
            name: Annotated[str, SendTo("field_name")]
            children: list[C] = []

        class A(BaseModel):
            children: list[B]
            names: list[str] = []

            def post_names(self, collector=Collector("field_name")):
                return collector.values()

        tree = A(
            children=[
                B(name="b1", children=[C(name="c1")]),
                B(name="b2", children=[]),
                B(name="b3", children=[]),
                B(name="b4", children=[C(name="c4")]),
            ]
        )
        result = await Resolver().resolve(tree)

        # Collector aggregates from ALL descendants (B and C)
        assert "b1" in result.names
        assert "b2" in result.names
        assert "b3" in result.names
        assert "b4" in result.names
        assert "c1!" in result.names
        assert "c4!" in result.names


# ──────────────────────────────────────────────────────────
# Test: Multi-field SendTo + flat/non-flat + Collector identity
# ──────────────────────────────────────────────────────────


class TestCollectorFlatNest:
    async def test_flat_collection(self):
        """flat=True flattens list values into a single list."""

        class C(BaseModel):
            detail: str
            details: Annotated[list[str], SendTo("c_details")] = []

            def resolve_details(self):
                return [f"{self.detail}-d1", f"{self.detail}-d2"]

        class BFlat(BaseModel):
            children: list[C]
            details_flat: list[str] = []

            def post_details_flat(self, collector=Collector("c_details", flat=True)):
                return collector.values()

        tree = BFlat(
            children=[
                C(detail="x-1"),
                C(detail="x-2"),
            ]
        )
        result = await Resolver().resolve(tree)

        assert result.details_flat == [
            "x-1-d1", "x-1-d2",
            "x-2-d1", "x-2-d2",
        ]

    async def test_nested_collection(self):
        """Without flat, list values are preserved as sublists."""

        class C(BaseModel):
            detail: str
            details: Annotated[list[str], SendTo("c_details")] = []

            def resolve_details(self):
                return [f"{self.detail}-d1", f"{self.detail}-d2"]

        class BNested(BaseModel):
            children: list[C]
            details_nested: list[list[str]] = []

            def post_details_nested(self, collector=Collector("c_details")):
                return collector.values()

        tree = BNested(
            children=[
                C(detail="x-1"),
                C(detail="x-2"),
            ]
        )
        result = await Resolver().resolve(tree)

        assert result.details_nested == [
            ["x-1-d1", "x-1-d2"],
            ["x-2-d1", "x-2-d2"],
        ]


# ──────────────────────────────────────────────────────────
# Test: Multiple fields send to same Collector (multi-value tuple)
# ──────────────────────────────────────────────────────────


class TestMultiFieldSendTo:
    async def test_multiple_fields_same_collector(self):
        """Multiple fields on same node can send to one Collector."""

        class Child(BaseModel):
            a: Annotated[int, SendTo("collector")]
            b: Annotated[int, SendTo("collector")]

        class Parent(BaseModel):
            children: list[Child]
            total: int = 0

            def post_total(self, collector=Collector("collector")):
                s = 0
                for val in collector.values():
                    s += val
                return s

        parent = Parent(children=[Child(a=1, b=2), Child(a=3, b=4)])
        result = await Resolver().resolve(parent)

        assert result.total == 10


# ──────────────────────────────────────────────────────────
# Test: SubsetConfig send_to parameter
# ──────────────────────────────────────────────────────────


class TestSubsetConfigSendTo:
    async def test_send_to_via_subset_config(self):
        """SubsetConfig.send_to should work like SendTo annotation."""

        from sqlmodel import Field, SQLModel

        class SourceModel(SQLModel, table=False):
            id: int | None = Field(default=None, primary_key=True)
            a: int
            b: int

        from nexusx.subset import DefineSubset, SubsetConfig

        class ChildDTO(DefineSubset):
            __subset__ = SubsetConfig(
                kls=SourceModel,
                fields=["a", "b"],
                send_to=[("a", "collector1"), ("b", "collector1")],
            )

        class ParentDTO(BaseModel):
            children: list[ChildDTO]
            total: int = 0

            def post_total(self, collector=Collector("collector1")):
                s = 0
                for val in collector.values():
                    s += val
                return s

        parent = ParentDTO(
            children=[ChildDTO(a=1, b=2), ChildDTO(a=3, b=4)]
        )
        result = await Resolver().resolve(parent)

        assert result.total == 10


# ──────────────────────────────────────────────────────────
# Test: post_* with Loader-resolved field — Collector not populated
# ──────────────────────────────────────────────────────────


class TestPostLoaderCollectorLimitation:
    async def test_collector_empty_after_loader_resolve(self):
        """post_* that uses Loader to resolve a field cannot collect from that field's descendants.

        BFS resolves the field via Loader, but the resolved children are not
        traversed for SendTo collection before the parent's post_* runs.
        So the Collector remains empty.
        """

        class Book(BaseModel):
            name: str

        async def book_loader(keys):
            return [
                [Book(name=f"book_{k}_1"), Book(name=f"book_{k}_2")]
                for k in keys
            ]

        class Student(BaseModel):
            id: int
            name: str
            books: list[Book] = []

            def resolve_books(self, loader=Loader(book_loader)):
                return loader.load(self.id)

            collected_book_names: list[str] = []

            def post_collected_book_names(self, collector=Collector("book_name")):
                return collector.values()

        students = [
            Student(id=1, name="jack"),
            Student(id=2, name="mike"),
        ]
        result = await Resolver().resolve(students)

        # books are loaded, but collector is empty because
        # resolve_* returns the value without traversing children for SendTo
        assert result[0].books == [Book(name="book_1_1"), Book(name="book_1_2")]
        assert result[0].collected_book_names == []


# ──────────────────────────────────────────────────────────
# Test: Collector identity — same alias in same post_* returns same instance
# ──────────────────────────────────────────────────────────


class TestCollectorIdentity:
    async def test_same_collector_twice_in_post(self):
        """Two Collector params with same alias in one post_* are the same instance."""

        class Child(BaseModel):
            name: Annotated[str, SendTo("names")]

        class Parent(BaseModel):
            children: list[Child] = []
            is_consistent: bool = False

            def post_is_consistent(
                self,
                c1=Collector("names"),
                c2=Collector("names"),
            ):
                return c1.values() == c2.values()

        parent = Parent(children=[Child(name="Alice"), Child(name="Bob")])
        result = await Resolver().resolve(parent)

        assert result.is_consistent is True


# ──────────────────────────────────────────────────────────
# Test: ICollector implementations and Collector subclasses
# (migrated from pydantic-resolve test_collector_subclass.py — #293)
#
# Before the deepcopy fix, _phase_b_prepare_collectors hardcoded
# `Collector(alias=alias, flat=flat)` when instantiating per-node collectors,
# which silently downgraded any:
#   - direct ICollector implementation (lost all __init__ config + wrong val)
#   - Collector subclass with extra __init__ config (lost the extra attrs)
# to the base Collector. deepcopy preserves the prototype transparently.
# ──────────────────────────────────────────────────────────


class MapCollector(ICollector):
    """ICollector with dict-valued state + key_fn config."""

    def __init__(self, alias: str, key_fn):
        self.alias = alias
        self.key_fn = key_fn
        self.val: dict = {}

    def add(self, val):
        self.val[self.key_fn(val)] = val

    def values(self):
        return list(self.val.values())


class TopNCollector(Collector):
    """Collector subclass with extra `n` config in __init__."""

    def __init__(self, alias, n):
        super().__init__(alias)
        self.n = n

    def add(self, val):
        self.val.append(val)
        if len(self.val) > self.n:
            self.val = self.val[-self.n:]


class SimpleSubCollector(Collector):
    """Only overrides add() — backward-compat baseline."""

    def add(self, val):
        self.val.append(f"sub-{val}")


class TestCollectorSubclass:
    async def test_map_collector_dedupes(self):
        """MapCollector (implements ICollector directly) must keep key_fn + dict val."""

        class Comment(BaseModel):
            email: Annotated[str, SendTo("unique_emails")]

        class Post(BaseModel):
            comments: list[Comment] = []
            unique_emails: list[str] = []

            def post_unique_emails(
                self,
                collector=MapCollector("unique_emails", key_fn=lambda v: v),
            ):
                return collector.values()

        post = Post(comments=[
            Comment(email="a@x.com"),
            Comment(email="a@x.com"),
            Comment(email="b@x.com"),
        ])
        result = await Resolver().resolve(post)
        assert sorted(result.unique_emails) == ["a@x.com", "b@x.com"]

    async def test_sibling_branches_isolated(self):
        """Each Post node must see only its own comments' unique_emails."""

        class Comment(BaseModel):
            email: Annotated[str, SendTo("unique_emails")]

        class Post(BaseModel):
            comments: list[Comment] = []
            unique_emails: list[str] = []

            def post_unique_emails(
                self,
                collector=MapCollector("unique_emails", key_fn=lambda v: v),
            ):
                return collector.values()

        class Root(BaseModel):
            posts: list[Post] = []

        root = Root(posts=[
            Post(comments=[Comment(email="a@x.com"), Comment(email="b@x.com")]),
            Post(comments=[Comment(email="c@x.com"), Comment(email="c@x.com")]),
        ])
        result = await Resolver().resolve(root)
        assert sorted(result.posts[0].unique_emails) == ["a@x.com", "b@x.com"]
        assert sorted(result.posts[1].unique_emails) == ["c@x.com"]

    async def test_sequential_resolve_no_leak(self):
        """Resolver reused across two trees must not carry collector state over."""

        class Comment(BaseModel):
            email: Annotated[str, SendTo("unique_emails")]

        class Post(BaseModel):
            comments: list[Comment] = []
            unique_emails: list[str] = []

            def post_unique_emails(
                self,
                collector=MapCollector("unique_emails", key_fn=lambda v: v),
            ):
                return collector.values()

        resolver = Resolver()
        p1 = await resolver.resolve(Post(comments=[Comment(email="a@x.com")]))
        p2 = await resolver.resolve(Post(comments=[Comment(email="b@x.com")]))
        assert p1.unique_emails == ["a@x.com"]
        assert p2.unique_emails == ["b@x.com"]

    async def test_topn_collector_preserves_n_config(self):
        """TopNCollector's `n` attr must survive per-node instantiation."""

        class Item(BaseModel):
            score: Annotated[int, SendTo("top_scores")]

        class Bucket(BaseModel):
            items: list[Item] = []
            top_scores: list[int] = []

            def post_top_scores(self, collector=TopNCollector("top_scores", n=2)):
                return collector.values()

        bucket = Bucket(items=[Item(score=i) for i in [10, 20, 30, 40]])
        result = await Resolver().resolve(bucket)
        assert result.top_scores == [30, 40]

    async def test_simple_subcollector_still_works(self):
        """Backward-compat: a Collector subclass that only overrides add()."""

        class Leaf(BaseModel):
            name: Annotated[str, SendTo("leaf_names")]

        class Branch(BaseModel):
            leaves: list[Leaf] = []
            decorated: list[str] = []

            def post_decorated(self, collector=SimpleSubCollector("leaf_names")):
                return collector.values()

        branch = Branch(leaves=[Leaf(name="a"), Leaf(name="b")])
        result = await Resolver().resolve(branch)
        assert result.decorated == ["sub-a", "sub-b"]
