"""Tests for Resolver — resolve_*, post_*, and Loader integration."""

from __future__ import annotations

import asyncio
from typing import Annotated

import pytest
from pydantic import BaseModel

from nexusx.resolver import Loader, Resolver

# ──────────────────────────────────────────────────────────
# Test: basic resolve_* with custom loaders
# ──────────────────────────────────────────────────────────

class TestResolverBasic:
    @pytest.mark.usefixtures("test_db")
    async def test_sync_resolve(self):
        """Sync resolve_* method should populate the field."""

        class SimpleModel(BaseModel):
            name: str
            greeting: str = ""

            def resolve_greeting(self):
                return f"Hello, {self.name}!"

        model = SimpleModel(name="Alice")
        result = await Resolver().resolve(model)

        assert result.greeting == "Hello, Alice!"

    @pytest.mark.usefixtures("test_db")
    async def test_async_resolve(self):
        """Async resolve_* method should work."""

        class AsyncModel(BaseModel):
            name: str
            greeting: str = ""

            async def resolve_greeting(self):
                await asyncio.sleep(0.01)
                return f"Hello, {self.name}!"

        model = AsyncModel(name="Alice")
        result = await Resolver().resolve(model)

        assert result.greeting == "Hello, Alice!"

    @pytest.mark.usefixtures("test_db")
    async def test_resolve_list(self):
        """Resolver should handle a list of models."""

        class Item(BaseModel):
            name: str
            label: str = ""

            def resolve_label(self):
                return f"Item: {self.name}"

        items = [Item(name="A"), Item(name="B"), Item(name="C")]
        result = await Resolver().resolve(items)

        assert result[0].label == "Item: A"
        assert result[1].label == "Item: B"
        assert result[2].label == "Item: C"


# ──────────────────────────────────────────────────────────
# Test: post_* methods
# ──────────────────────────────────────────────────────────

class TestResolverPost:
    @pytest.mark.usefixtures("test_db")
    async def test_post_method(self):
        """post_* should execute after resolve_* completes."""

        class Counter(BaseModel):
            values: list[int] = []
            total: int = 0
            count: int = 0

            def resolve_values(self):
                return [1, 2, 3]

            def post_total(self):
                return sum(self.values)

            def post_count(self):
                return len(self.values)

        model = Counter()
        result = await Resolver().resolve(model)

        assert result.values == [1, 2, 3]
        assert result.total == 6
        assert result.count == 3

    @pytest.mark.usefixtures("test_db")
    async def test_post_accesses_resolved_data(self):
        """post_* can access fields populated by resolve_*."""

        class Model(BaseModel):
            name: str = "World"
            greeting: str = ""

            def resolve_name(self):
                return "Alice"

            def post_greeting(self):
                return f"Hello, {self.name}!"

        model = Model()
        result = await Resolver().resolve(model)

        assert result.name == "Alice"
        assert result.greeting == "Hello, Alice!"

    @pytest.mark.usefixtures("test_db")
    async def test_post_with_parent(self):
        """post_* can access parent node via parent parameter."""

        class Child(BaseModel):
            name: str
            parent_name: str = ""

            def post_parent_name(self, parent=None):
                if parent:
                    return f"child of {parent.name}"
                return "no parent"

        class Parent(BaseModel):
            name: str
            children: list[Child] = []

        parent = Parent(
            name="Parent1",
            children=[
                Child(name="Child1"),
                Child(name="Child2"),
            ],
        )
        result = await Resolver().resolve(parent)

        assert result.children[0].parent_name == "child of Parent1"
        assert result.children[1].parent_name == "child of Parent1"


# ──────────────────────────────────────────────────────────
# Test: nested resolve with DefineSubset
# ──────────────────────────────────────────────────────────

class TestResolverNested:
    @pytest.mark.usefixtures("test_db")
    async def test_post_on_nested_subset(self):
        """post_* on DefineSubset should work after resolve_*."""

        class SimpleParent(BaseModel):
            name: str
            items: list[str] = []
            item_count: int = 0

            def resolve_items(self):
                return ["a", "b", "c"]

            def post_item_count(self):
                return len(self.items)

        model = SimpleParent(name="test")
        result = await Resolver().resolve(model)

        assert result.items == ["a", "b", "c"]
        assert result.item_count == 3


# ──────────────────────────────────────────────────────────
# Test: context parameter
# ──────────────────────────────────────────────────────────

class TestResolverContext:
    async def test_context_in_resolve(self):
        """resolve_* can access context parameter."""

        class Model(BaseModel):
            name: str
            greeting: str = ""

            def resolve_greeting(self, context=None):
                if context is None:
                    context = {}
                prefix = context.get("prefix", "Hello")
                return f"{prefix}, {self.name}!"

        result = await Resolver(context={"prefix": "Hi"}).resolve(Model(name="Alice"))
        assert result.greeting == "Hi, Alice!"

    async def test_context_in_post(self):
        """post_* can access context parameter."""

        class Model(BaseModel):
            name: str
            suffix: str = ""

            def post_suffix(self, context=None):
                if context is None:
                    context = {}
                return context.get("suffix", "")

        result = await Resolver(context={"suffix": "(admin)"}).resolve(
            Model(name="Alice")
        )
        assert result.suffix == "(admin)"


# ──────────────────────────────────────────────────────────
# Test: exception handling
# ──────────────────────────────────────────────────────────


class TestResolverExceptions:
    async def test_resolve_method_raises_exception(self):
        """Exception in resolve_* should propagate."""

        class Model(BaseModel):
            name: str
            value: str = ""

            def resolve_value(self):
                raise ValueError("resolve failed")

        with pytest.raises(ValueError, match="resolve failed"):
            await Resolver().resolve(Model(name="test"))

    async def test_post_method_raises_exception(self):
        """Exception in post_* should propagate."""

        class Model(BaseModel):
            name: str
            summary: str = ""

            def post_summary(self):
                raise RuntimeError("post failed")

        with pytest.raises(RuntimeError, match="post failed"):
            await Resolver().resolve(Model(name="test"))

    async def test_resolve_returns_wrong_type_does_not_crash(self):
        """resolve_* returning unexpected type should not crash Resolver."""

        class Model(BaseModel):
            name: str
            items: list[str] = []

            def resolve_items(self):
                # Returns a string instead of list[str]
                return "not a list"

        # Resolver should complete without error (Pydantic will coerce or validate)
        result = await Resolver().resolve(Model(name="test"))
        # The field gets the raw return value
        assert result.items == "not a list"


# ──────────────────────────────────────────────────────────
# Test: async post_* methods
# ──────────────────────────────────────────────────────────


class TestResolverAsyncPost:
    async def test_async_post_method(self):
        """async def post_* should execute correctly."""

        class Model(BaseModel):
            name: str
            processed_name: str = ""

            async def post_processed_name(self):
                await asyncio.sleep(0.01)
                return self.name.upper()

        result = await Resolver().resolve(Model(name="alice"))
        assert result.processed_name == "ALICE"

    async def test_async_post_accesses_resolved_data(self):
        """async post_* should access data populated by resolve_*."""

        class Child(BaseModel):
            name: str = ""
            resolved_label: str = ""

            def resolve_name(self):
                return "resolved_child"

            async def post_resolved_label(self):
                await asyncio.sleep(0.01)
                return f"label:{self.name}"

        class Parent(BaseModel):
            children: list[Child] = []

        parent = Parent(children=[Child()])
        result = await Resolver().resolve(parent)

        assert result.children[0].name == "resolved_child"
        assert result.children[0].resolved_label == "label:resolved_child"


# ──────────────────────────────────────────────────────────
# Test: parent parameter in resolve_*
# ──────────────────────────────────────────────────────────


class TestResolverParentParameter:
    async def test_resolve_with_parent(self):
        """resolve_* should receive parent node via parent parameter."""

        class Child(BaseModel):
            name: str
            parent_label: str = ""

            def resolve_parent_label(self, parent=None):
                if parent:
                    return f"from:{parent.name}"
                return "no parent"

        class Parent(BaseModel):
            name: str
            children: list[Child] = []

        parent = Parent(
            name="Root",
            children=[Child(name="C1"), Child(name="C2")],
        )
        result = await Resolver().resolve(parent)

        assert result.children[0].parent_label == "from:Root"
        assert result.children[1].parent_label == "from:Root"

    async def test_parent_in_nested_resolve(self):
        """Parent parameter should work in deeply nested structures."""

        class Leaf(BaseModel):
            value: str
            path: str = ""

            def resolve_path(self, parent=None):
                if parent:
                    return f"{parent.label}/{self.value}"
                return self.value

        class Branch(BaseModel):
            label: str
            leaves: list[Leaf] = []

        class Tree(BaseModel):
            name: str
            branches: list[Branch] = []

        tree = Tree(
            name="T",
            branches=[
                Branch(label="B1", leaves=[Leaf(value="L1"), Leaf(value="L2")]),
                Branch(label="B2", leaves=[Leaf(value="L3")]),
            ],
        )
        result = await Resolver().resolve(tree)

        assert result.branches[0].leaves[0].path == "B1/L1"
        assert result.branches[0].leaves[1].path == "B1/L2"
        assert result.branches[1].leaves[0].path == "B2/L3"


# ──────────────────────────────────────────────────────────
# Test: advanced post_* combinations
# ──────────────────────────────────────────────────────────


class TestResolverPostAdvanced:
    async def test_post_aggregation_after_nested_resolve(self):
        """post_* should aggregate data from nested resolve_* results."""

        class Item(BaseModel):
            value: int = 0

            def resolve_value(self):
                return self.value * 10

        class Container(BaseModel):
            items: list[Item] = []
            total: int = 0
            max_value: int = 0

            def resolve_items(self):
                return [Item(value=1), Item(value=2), Item(value=3)]

            def post_total(self):
                return sum(item.value for item in self.items)

            def post_max_value(self):
                return max(item.value for item in self.items) if self.items else 0

        result = await Resolver().resolve(Container())

        # resolve_items runs first → items populated
        # resolve_value runs on each item → values become 10, 20, 30
        # post_total/post_max_value run after all resolves
        assert result.items[0].value == 10
        assert result.items[1].value == 20
        assert result.items[2].value == 30
        assert result.total == 60
        assert result.max_value == 30

    async def test_post_with_context_aggregation(self):
        """post_* should use context for conditional aggregation."""

        class Item(BaseModel):
            name: str
            category: str = ""

            def post_category(self, context=None):
                if context is None:
                    context = {}
                prefix = context.get("prefix", "")
                return f"{prefix}:{self.name}"

        class Group(BaseModel):
            items: list[Item] = []
            categories: list[str] = []

            def post_categories(self):
                return [item.category for item in self.items]

        group = Group(
            items=[
                Item(name="A"),
                Item(name="B"),
            ]
        )
        result = await Resolver(context={"prefix": "CAT"}).resolve(group)

        assert result.items[0].category == "CAT:A"
        assert result.items[1].category == "CAT:B"
        assert result.categories == ["CAT:A", "CAT:B"]

    async def test_post_order_depends_on_resolve(self):
        """post_* must execute strictly after resolve_* completes."""

        execution_order = []

        class Model(BaseModel):
            name: str = ""
            computed: str = ""

            def resolve_name(self):
                execution_order.append("resolve")
                return "resolved"

            def post_computed(self):
                execution_order.append("post")
                return f"computed:{self.name}"

        await Resolver().resolve(Model())

        assert execution_order == ["resolve", "post"]


# ──────────────────────────────────────────────────────────
# Test: BFS edge cases — uncovered paths
# ──────────────────────────────────────────────────────────


class TestBfsEdgeCases:
    async def test_empty_list_input(self):
        """Resolver should handle an empty list without error."""
        result = await Resolver().resolve([])
        assert result == []

    async def test_non_basemodel_input(self):
        """Non-BaseModel input should be returned as-is."""
        result = await Resolver().resolve("just a string")
        assert result == "just a string"

    async def test_tuple_input(self):
        """Resolver should accept a tuple of BaseModel instances."""

        class Item(BaseModel):
            name: str
            label: str = ""

            def resolve_label(self):
                return f"label:{self.name}"

        items = (Item(name="A"), Item(name="B"))
        result = await Resolver().resolve(items)
        assert isinstance(result, tuple)
        assert result[0].label == "label:A"
        assert result[1].label == "label:B"

    async def test_mixed_list_filters_non_basemodel(self):
        """Non-BaseModel items in a list should be silently skipped."""

        class Item(BaseModel):
            name: str
            label: str = ""

            def resolve_label(self):
                return f"label:{self.name}"

        items = [Item(name="A"), "not a model", Item(name="B")]
        result = await Resolver().resolve(items)
        assert result[0].label == "label:A"
        assert result[1] == "not a model"
        assert result[2].label == "label:B"

    async def test_resolve_returns_tuple_of_basemodels(self):
        """resolve_* returning a tuple should traverse children."""

        class Child(BaseModel):
            name: str
            label: str = ""

            def resolve_label(self):
                return f"child:{self.name}"

        class Parent(BaseModel):
            children: tuple[Child, ...] = ()

            def resolve_children(self):
                return (Child(name="A"), Child(name="B"))

        result = await Resolver().resolve(Parent())
        assert result.children[0].label == "child:A"
        assert result.children[1].label == "child:B"

    async def test_resolve_returns_list_with_non_basemodel(self):
        """Non-BaseModel items in resolve_* result list are skipped."""

        class Child(BaseModel):
            name: str

        class Parent(BaseModel):
            items: list = []

            def resolve_items(self):
                return [Child(name="A"), "skip me", Child(name="B")]

        result = await Resolver().resolve(Parent())
        assert len(result.items) == 3
        assert isinstance(result.items[0], Child)
        assert result.items[1] == "skip me"

    async def test_resolve_with_ancestor_context(self):
        """resolve_* should receive ancestor_context from parent ExposeAs."""


        from nexusx.context import ExposeAs

        class Child(BaseModel):
            name: str
            parent_prefix: str = ""

            def resolve_parent_prefix(self, ancestor_context=None):
                if ancestor_context is None:
                    ancestor_context = {}
                return ancestor_context.get("prefix", "none")

        class Parent(BaseModel):
            prefix: Annotated[str, ExposeAs("prefix")]
            children: list[Child] = []

        parent = Parent(
            prefix="HELLO",
            children=[Child(name="A"), Child(name="B")],
        )
        result = await Resolver().resolve(parent)
        assert result.children[0].parent_prefix == "HELLO"
        assert result.children[1].parent_prefix == "HELLO"


# ──────────────────────────────────────────────────────────
# Test: P0 — post_* with Loader, _orm_to_dto, _do_extract_dto_cls
# ──────────────────────────────────────────────────────────


class TestPostWithLoader:
    async def test_post_with_loader_dep(self):
        """post_* should receive Loader-injected DataLoader."""

        async def double_loader(keys):
            return [k * 2 for k in keys]

        class Item(BaseModel):
            val: int
            doubled: int = 0

            def post_doubled(self, loader=Loader(double_loader)):
                return loader.load(self.val)

        result = await Resolver().resolve(Item(val=5))
        assert result.doubled == 10

    async def test_post_with_collector_and_loader(self):
        """post_* should receive both Collector and Loader parameters."""


        from nexusx.context import Collector, SendTo

        async def tag_loader(keys):
            return [f"tag_{k}" for k in keys]

        class Child(BaseModel):
            val: int
            tag: Annotated[str, SendTo("vals")] = ""

            def post_tag(self, loader=Loader(tag_loader)):
                return loader.load(self.val)

        class Parent(BaseModel):
            children: list[Child] = []
            collected_vals: list[str] = []
            summary: str = ""

            def post_collected_vals(self, collector=Collector("vals")):
                return collector.values()

            def post_summary(self, loader=Loader(tag_loader)):
                return loader.load(99)

        parent = Parent(children=[Child(val=1), Child(val=2)])
        result = await Resolver().resolve(parent)

        assert result.children[0].tag == "tag_1"
        assert result.children[1].tag == "tag_2"
        assert "tag_1" in result.collected_vals
        assert "tag_2" in result.collected_vals
        assert result.summary == "tag_99"


class TestLoaderInstances:
    """Tests for ``Resolver(loader_instances=...)`` — pre-created DataLoader instances.

    Covers spec feature 002:
    - US1: pre-primed value observed, batch call suppressed for primed key.
    - US2: supplied instance used by reference, constructor state preserved.
    - US3: misuse fails fast at construction with TypeError.
    """

    async def test_loader_instances_pre_prime(self):
        """US1: primed keys hit cache; batch runs only for unprimed keys."""
        from aiodataloader import DataLoader

        batch_calls: list[list[int]] = []

        class CountingLoader(DataLoader):
            async def batch_load_fn(self, keys):
                batch_calls.append(list(keys))
                return [f"value_{k}" for k in keys]

        loader = CountingLoader()
        loader.prime(42, "primed_value_42")

        class Item(BaseModel):
            val: int
            loaded: str = ""

            def resolve_loaded(self, loader=Loader(CountingLoader)):
                return loader.load(self.val)

        items = [Item(val=42), Item(val=7)]
        result = await Resolver(loader_instances={CountingLoader: loader}).resolve(items)

        # Primed value observed, batch NOT triggered for key 42.
        assert result[0].loaded == "primed_value_42"
        # Unprimed key falls through to batch.
        assert result[1].loaded == "value_7"
        # Exactly one batch dispatch (containing only the unprimed key).
        assert batch_calls == [[7]]

    async def test_loader_instances_by_reference(self):
        """US2: supplied loader instance stays by reference with state intact."""
        from aiodataloader import DataLoader

        class TaggedLoader(DataLoader):
            def __init__(self, tag: str = "default", **kwargs):
                super().__init__(**kwargs)
                self.tag = tag

            async def batch_load_fn(self, keys):
                return [f"{self.tag}_{k}" for k in keys]

        captured: list = []
        supplied = TaggedLoader(tag="abc")

        class Item(BaseModel):
            val: int
            tag: str = ""

            def resolve_tag(self, loader=Loader(TaggedLoader)):
                captured.append(loader)
                return loader.load(self.val)

        result = await Resolver(loader_instances={TaggedLoader: supplied}).resolve(
            Item(val=1)
        )

        assert result.tag == "abc_1"
        assert len(captured) == 1
        # Same instance by identity.
        assert captured[0] is supplied
        # Constructor state preserved.
        assert captured[0].tag == "abc"

    async def test_loader_instances_validation_errors(self):
        """US3: malformed input fails at construction with a typed error."""
        from aiodataloader import DataLoader

        class ValidLoader(DataLoader):
            async def batch_load_fn(self, keys):
                return keys

        # Non-DataLoader key.
        with pytest.raises(TypeError, match="must be a subclass of aiodataloader.DataLoader"):
            Resolver(loader_instances={dict: object()})

        # Value not an instance of the key class.
        with pytest.raises(TypeError, match=r"must be an instance of ValidLoader"):
            Resolver(loader_instances={ValidLoader: object()})

        # Empty dict and None must succeed.
        Resolver(loader_instances={})
        Resolver()
        Resolver(loader_instances=None)


class TestOrmToDto:
    def test_orm_to_dto_without_subset_fields(self):
        """_orm_to_dto should use model_validate when no __subset_fields__."""

        class PlainDTO(BaseModel):
            name: str
            value: int

        # model_validate accepts dict-like objects
        result = Resolver._orm_to_dto({"name": "test", "value": 42}, PlainDTO)
        assert result.name == "test"
        assert result.value == 42

    def test_orm_to_dto_preserves_null_for_optional_field(self):
        """A NULL-loaded ORM value must be preserved as None on the DTO,
        not replaced by the field's declared default.

        Regression test for the silent-NULL-replacement bug at
        resolver.py:654 (was: `if v is not None` filtered out None
        values, causing dto_cls(**kwargs) to fall back to Field(default)).
        """
        from types import SimpleNamespace

        from sqlmodel import Field, SQLModel

        from nexusx import DefineSubset

        class ScoreEntity(SQLModel):
            id: int | None = Field(default=None, primary_key=True)
            name: str
            # Nullable column with a non-None default — common pattern for
            # "metric that defaults to 0 when missing".
            score: int | None = Field(default=0)

        class ScoreDTO(DefineSubset):
            __subset__ = (ScoreEntity, ("id", "name", "score"))

        # Simulate an ORM instance loaded from a row where score IS NULL.
        # (Direct `ScoreEntity(score=None)` would let SQLModel substitute
        # the Python-side default of 0; raw SQL or server-side defaults
        # bypass that, producing a genuine None on the loaded instance.)
        orm_with_null = SimpleNamespace(id=1, name="legacy_row", score=None)

        dto = Resolver._orm_to_dto(orm_with_null, ScoreDTO)

        # NULL must round-trip as None — not collapse into Field(default=0).
        assert dto.score is None, (
            f"Expected None (preserved NULL), got {dto.score!r}. "
            f"If the DTO field has a non-None default, this means NULL "
            f"and 'explicit 0' are indistinguishable in API responses."
        )

    def test_orm_to_dto_preserves_explicit_zero(self):
        """Counter-test: an explicit 0 must round-trip as 0 (not None)."""
        from types import SimpleNamespace

        from sqlmodel import Field, SQLModel

        from nexusx import DefineSubset

        class ScoreEntity(SQLModel):
            id: int | None = Field(default=None, primary_key=True)
            name: str
            score: int | None = Field(default=0)

        class ScoreDTO(DefineSubset):
            __subset__ = (ScoreEntity, ("id", "name", "score"))

        orm_with_zero = SimpleNamespace(id=1, name="explicit_zero", score=0)
        dto = Resolver._orm_to_dto(orm_with_zero, ScoreDTO)

        assert dto.score == 0
        assert dto.score is not None

    def test_orm_to_dto_typo_in_string_annotation_propagates(self):
        """A typo in a DTO's string annotation must propagate — not be
        silently swallowed by an aggressive fallback.

        Guards against re-introducing the pre-removal try/except wrapper
        at ``_orm_to_dto`` that retried via ``model_rebuild``. The old
        fallback was dead code under Pydantic 2 (auto-resolves forward
        refs at class creation), but if someone re-adds similar logic
        they could mask real schema bugs (typos, missing imports).
        """
        from types import SimpleNamespace

        from sqlmodel import Field, SQLModel

        from nexusx import DefineSubset

        class TypoEntity(SQLModel):
            id: int | None = Field(default=None, primary_key=True)
            name: str

        class TypoDTO(DefineSubset):
            __subset__ = (TypoEntity, ("id", "name"))
            # Forward ref to a class that doesn't exist anywhere — simulates
            # a real-world typo or missing import.
            __annotations__ = {"child": "NonExistentClassXYZ | None"}
            child = None

        orm = SimpleNamespace(id=1, name="x")
        with pytest.raises(Exception, match="NonExistentClassXYZ"):
            Resolver._orm_to_dto(orm, TypoDTO)


class TestExtractDtoCls:
    def test_string_annotation_returns_none(self):
        """String annotations should return None."""
        from pydantic.fields import FieldInfo

        fi = FieldInfo(annotation="SomeForwardRef")
        assert Resolver()._extract_dto_cls(fi) is None

    def test_pure_none_type_returns_none(self):
        """type(None) as annotation should return None."""
        from pydantic.fields import FieldInfo

        fi = FieldInfo(annotation=type(None))
        assert Resolver()._extract_dto_cls(fi) is None

    def test_plain_int_returns_none(self):
        """Non-BaseModel types should return None."""
        from pydantic.fields import FieldInfo

        fi = FieldInfo(annotation=int)
        assert Resolver()._extract_dto_cls(fi) is None

    def test_basemodel_in_optional_returns_cls(self):
        """BaseModel inside Optional should be extracted."""

        class MyDTO(BaseModel):
            x: int

        from pydantic.fields import FieldInfo

        fi = FieldInfo(annotation=MyDTO | None)
        result = Resolver()._extract_dto_cls(fi)
        assert result is MyDTO

    def test_basemodel_in_list_returns_cls(self):
        """BaseModel inside list should be extracted."""

        class MyDTO(BaseModel):
            x: int

        from pydantic.fields import FieldInfo

        fi = FieldInfo(annotation=list[MyDTO])
        result = Resolver()._extract_dto_cls(fi)
        assert result is MyDTO


# ──────────────────────────────────────────────────────────
# Test: should_traverse optimization
# ──────────────────────────────────────────────────────────


class TestShouldTraverse:
    async def test_traverses_through_passthrough_node_to_leaf_with_post(self):
        """Intermediate node without methods should still be traversed if descendant has post_*."""

        class Leaf(BaseModel):
            value: str
            processed: str = ""

            def post_processed(self):
                return f"processed_{self.value}"

        class Middle(BaseModel):
            name: str
            leaf: Leaf

        class Root(BaseModel):
            middle: Middle

        root = Root(middle=Middle(name="M1", leaf=Leaf(value="V1")))
        result = await Resolver().resolve(root)

        assert result.middle.leaf.processed == "processed_V1"

    async def test_shared_type_at_multiple_levels(self):
        """Same DTO class at different depths should work correctly."""

        class Tag(BaseModel):
            label: str
            display: str = ""

            def post_display(self):
                return f"[{self.label}]"

        class Item(BaseModel):
            name: str
            tag: Tag

        class Container(BaseModel):
            items: list[Item]
            top_tag: Tag

        container = Container(
            items=[
                Item(name="A", tag=Tag(label="t1")),
                Item(name="B", tag=Tag(label="t2")),
            ],
            top_tag=Tag(label="top"),
        )
        result = await Resolver().resolve(container)

        assert result.top_tag.display == "[top]"
        assert result.items[0].tag.display == "[t1]"
        assert result.items[1].tag.display == "[t2]"

    async def test_expose_as_prevents_skip(self):
        """Nodes with ExposeAs should not be skipped."""


        from nexusx.context import ExposeAs

        class Child(BaseModel):
            name: str
            context_val: str = ""

            def post_context_val(self, ancestor_context=None):
                if ancestor_context is None:
                    ancestor_context = {}
                return ancestor_context.get("greeting", "")

        class Parent(BaseModel):
            greeting: Annotated[str, ExposeAs("greeting")]
            child: Child

        parent = Parent(greeting="Hello", child=Child(name="C1"))
        result = await Resolver().resolve(parent)

        assert result.child.context_val == "Hello"

    async def test_send_to_prevents_skip(self):
        """Nodes with SendTo should not be skipped."""


        from nexusx.context import Collector, SendTo

        class Child(BaseModel):
            value: Annotated[int, SendTo("values")]

        class Parent(BaseModel):
            child: Child
            total: int = 0

            def post_total(self, collector=Collector("values")):
                vals = collector.values()
                return sum(vals) if vals else 0

        parent = Parent(child=Child(value=42))
        result = await Resolver().resolve(parent)

        assert result.total == 42

    async def test_self_referencing_type(self):
        """Self-referencing types should handle cycles gracefully."""

        class TreeNode(BaseModel):
            name: str
            display_name: str = ""
            children: list[TreeNode] = []

            def post_display_name(self):
                return f"Node({self.name})"

        TreeNode.model_rebuild()

        tree = TreeNode(
            name="root",
            children=[
                TreeNode(name="child1", children=[]),
                TreeNode(name="child2", children=[]),
            ],
        )
        result = await Resolver().resolve(tree)

        assert result.display_name == "Node(root)"
        assert result.children[0].display_name == "Node(child1)"
        assert result.children[1].display_name == "Node(child2)"

    async def test_deep_hierarchy_traverses_to_leaf(self):
        """Multiple levels of passthrough nodes should still reach leaves with methods."""

        class DeepLeaf(BaseModel):
            value: int
            doubled: int = 0

            def post_doubled(self):
                return self.value * 2

        class Level3(BaseModel):
            data: str
            leaf: DeepLeaf

        class Level2(BaseModel):
            child: Level3

        class Level1(BaseModel):
            child: Level2

        root = Level1(child=Level2(child=Level3(data="d3", leaf=DeepLeaf(value=5))))
        result = await Resolver().resolve(root)

        assert result.child.child.leaf.doubled == 10

    async def test_cache_consistency_across_invocations(self):
        """should_traverse cache should be consistent across resolve() calls."""

        class Simple(BaseModel):
            name: str
            greeting: str = ""

            def resolve_greeting(self):
                return f"Hi, {self.name}"

        result1 = await Resolver().resolve(Simple(name="A"))
        assert result1.greeting == "Hi, A"

        result2 = await Resolver().resolve(Simple(name="B"))
        assert result2.greeting == "Hi, B"

    async def test_pure_data_node_is_skipped(self):
        """A child with no methods and no descendants with methods should not be traversed."""

        class PureData(BaseModel):
            name: str

        class Root(BaseModel):
            data: PureData
            greeting: str = ""

            def resolve_greeting(self):
                return "hello"

        root = Root(data=PureData(name="test"))
        result = await Resolver().resolve(root)

        assert result.greeting == "hello"
        assert result.data.name == "test"

    async def test_list_of_pure_data_nodes_is_skipped(self):
        """A list of children with no methods should not be traversed."""

        class PureItem(BaseModel):
            name: str

        class Root(BaseModel):
            items: list[PureItem] = []
            count: int = 0

            def post_count(self):
                return 42

        root = Root(items=[PureItem(name="A"), PureItem(name="B")])
        result = await Resolver().resolve(root)

        assert result.count == 42
        assert len(result.items) == 2

    async def test_descendant_with_resolve_triggers_traversal(self):
        """Intermediate node should be traversed if descendant has resolve_* (not just post_*)."""

        class Leaf(BaseModel):
            source_id: int
            source_name: str = ""

            def resolve_source_name(self):
                return f"source_{self.source_id}"

        class Middle(BaseModel):
            leaf: Leaf

        class Root(BaseModel):
            middle: Middle

        root = Root(middle=Middle(leaf=Leaf(source_id=5)))
        result = await Resolver().resolve(root)

        assert result.middle.leaf.source_name == "source_5"


# ──────────────────────────────────────────────────────────
# Test: post_default_handler — finalization hook (runs after all post_*)
# ──────────────────────────────────────────────────────────


class TestResolverPostDefaultHandler:
    async def test_runs_after_all_post_methods(self):
        """post_default_handler runs after every post_* at the same node,
        so it can read fields those post_* methods populated."""

        class Sprint(BaseModel):
            total_tasks: int = 0
            completed_tasks: int = 0
            completion_rate: float = 0.0

            def post_total_tasks(self):
                return 10

            def post_completed_tasks(self):
                return 4

            def post_default_handler(self):
                self.completion_rate = (
                    self.completed_tasks / self.total_tasks
                    if self.total_tasks
                    else 0.0
                )

        result = await Resolver().resolve(Sprint())
        assert result.total_tasks == 10
        assert result.completed_tasks == 4
        assert result.completion_rate == 0.4

    async def test_return_value_ignored_and_no_field_auto_assigned(self):
        """The handler's return value is NOT auto-assigned to any field
        (in particular, no spurious `default_handler` field is created),
        and the body may set several fields manually."""

        class Model(BaseModel):
            a: int = 0
            b: int = 0

            def post_default_handler(self):
                self.a = 1
                self.b = 2
                return "this return value must be ignored"

        result = await Resolver().resolve(Model())
        assert result.a == 1
        assert result.b == 2
        # No field named after the method is created.
        assert not hasattr(result, "default_handler")

    async def test_async_handler(self):
        """async def post_default_handler is awaited correctly."""

        class Model(BaseModel):
            value: int = 0

            async def post_default_handler(self):
                await asyncio.sleep(0)
                self.value = 42

        result = await Resolver().resolve(Model())
        assert result.value == 42

    async def test_handler_reads_collector_populated_by_descendants(self):
        """post_default_handler can read a Collector that descendants
        populated via SendTo — recursion finishes before the handler runs."""


        from nexusx.context import Collector, SendTo

        class Task(BaseModel):
            id: Annotated[int, SendTo("task_ids")]

        class Sprint(BaseModel):
            tasks: list[Task] = []
            task_ids: list[int] = []

            def post_default_handler(self, collector=Collector("task_ids")):
                self.task_ids = sorted(collector.values())

        sprint = Sprint(tasks=[Task(id=3), Task(id=1), Task(id=2)])
        result = await Resolver().resolve(sprint)
        assert result.task_ids == [1, 2, 3]

    async def test_handler_with_context(self):
        """The context parameter is injected from Resolver(context=...)."""

        class Model(BaseModel):
            label: str = ""

            def post_default_handler(self, context=None):
                if context is None:
                    context = {}
                self.label = context.get("env", "unknown")

        result = await Resolver(context={"env": "prod"}).resolve(Model())
        assert result.label == "prod"

    async def test_handler_with_parent(self):
        """The parent parameter references the direct parent node."""

        class Child(BaseModel):
            parent_name: str = ""

            def post_default_handler(self, parent=None):
                self.parent_name = getattr(parent, "name", "?") if parent else "?"

        class Parent(BaseModel):
            name: str
            child: Child

        result = await Resolver().resolve(
            Parent(name="Root", child=Child())
        )
        assert result.child.parent_name == "Root"

    async def test_handler_with_ancestor_context(self):
        """The ancestor_context parameter receives ExposeAs values."""


        from nexusx.context import ExposeAs

        class Leaf(BaseModel):
            tenant_label: str = ""

            def post_default_handler(self, ancestor_context=None):
                if ancestor_context is None:
                    ancestor_context = {}
                self.tenant_label = f"tenant={ancestor_context.get('tenant')}"

        class Middle(BaseModel):
            leaf: Leaf

        class Root(BaseModel):
            tenant: Annotated[str, ExposeAs("tenant")] = "acme"
            middle: Middle

        result = await Resolver().resolve(
            Root(tenant="acme", middle=Middle(leaf=Leaf()))
        )
        assert result.middle.leaf.tenant_label == "tenant=acme"

    async def test_handler_only_class_still_executes(self):
        """A child node whose ONLY hook is post_default_handler must still
        be traversed (regression: _compute_should_traverse must count it)."""

        class Child(BaseModel):
            name: str
            processed: bool = False

            def post_default_handler(self):
                self.processed = True

        class Parent(BaseModel):
            child: Child

        result = await Resolver().resolve(Parent(child=Child(name="x")))
        assert result.child.processed is True

    async def test_handler_runs_after_post_on_every_node_at_level(self):
        """When multiple sibling nodes each have post_* + post_default_handler,
        every node's handler runs after that node's post_* — independent of
        ordering across siblings."""

        class Counter(BaseModel):
            n: int
            doubled: int = 0
            quadrupled: int = 0

            def post_doubled(self):
                return self.n * 2

            def post_default_handler(self):
                # reads the post_doubled value written moments ago
                self.quadrupled = self.doubled * 2

        root = [Counter(n=1), Counter(n=5), Counter(n=10)]
        result = await Resolver().resolve(root)
        assert [r.doubled for r in result] == [2, 10, 20]
        assert [r.quadrupled for r in result] == [4, 20, 40]

    def test_conflict_when_default_handler_field_also_exists(self):
        """When a class declares BOTH:
          - a method named ``post_default_handler`` (reserved finalizer)
          - a field named ``default_handler``

        the framework must raise. The naming pattern ``post_<field>`` strongly
        suggests ``post_default_handler`` would populate a ``default_handler``
        field — but it doesn't (reserved as a finalizer, no auto-binding).
        Silently allowing this is a semantic trap.

        Regression for BUG_1_6 silent-reserved-name issue. The fix preserves
        backward compatibility: ``post_default_handler`` keeps its finalizer
        behavior when no ``default_handler`` field exists; it only fails loud
        when the conflict is unambiguous.
        """
        from pydantic import BaseModel

        from nexusx.resolver import _get_class_meta

        class ConflictingDTO(BaseModel):
            default_handler: str = ""

            def post_default_handler(self):
                return "would be silently discarded"

        with pytest.raises(ValueError, match="post_default_handler"):
            _get_class_meta(ConflictingDTO)

    def test_no_conflict_when_only_method_exists(self):
        """Counter-test: ``post_default_handler`` alone (no field) keeps
        working as the reserved finalizer."""
        from pydantic import BaseModel

        from nexusx.resolver import _get_class_meta

        class FinalizerOnly(BaseModel):
            label: str = ""

            def post_default_handler(self):
                self.label = "finalized"

        # Should not raise — finalizer behavior preserved.
        meta = _get_class_meta(FinalizerOnly)
        assert meta.post_default_handler is not None

    def test_no_conflict_when_only_field_exists(self):
        """Counter-test: ``default_handler`` field alone (no reserved method)
        is just a regular field — nothing special."""
        from pydantic import BaseModel

        from nexusx.resolver import _get_class_meta

        class FieldOnly(BaseModel):
            default_handler: str = "ok"

        # Should not raise — field is a plain Pydantic attribute.
        meta = _get_class_meta(FieldOnly)
        assert meta.post_default_handler is None
        assert "default_handler" in FieldOnly.model_fields


# ──────────────────────────────────────────────────────────
# Test: two-phase iterative resolver (post_* concurrency + immediate setattr)
# Regression coverage for the Phase A / Phase B refactor — see issue #77.
# ──────────────────────────────────────────────────────────


class TestResolverTwoPhase:
    async def test_post_concurrent_execution(self):
        """All post_* methods at the same level run concurrently via gather.

        Serial: 10 nodes × 3 posts × 50ms = 1.5s
        Concurrent (within node): 3 × 50ms gathered = 50ms per node
        Concurrent (across nodes at same level): 10 × 50ms gathered = 50ms total
        Asserting < 0.5s leaves headroom for slow CI.
        """
        import time

        class HeavyPost(BaseModel):
            id: int
            a: str = ""
            b: str = ""
            c: str = ""

            async def post_a(self):
                await asyncio.sleep(0.05)
                return f"a-{self.id}"

            async def post_b(self):
                await asyncio.sleep(0.05)
                return f"b-{self.id}"

            async def post_c(self):
                await asyncio.sleep(0.05)
                return f"c-{self.id}"

        nodes = [HeavyPost(id=i) for i in range(10)]

        t0 = time.perf_counter()
        result = await Resolver().resolve(nodes)
        elapsed = time.perf_counter() - t0

        # 10 nodes × 3 posts × 0.05s = 1.5s serial. Concurrent ≤ 0.05s.
        # Threshold 0.5s tolerates CI jitter while still failing on serial code.
        assert elapsed < 0.5, (
            f"post_* took {elapsed:.2f}s — expected concurrent (<0.5s), "
            f"serial would be ~1.5s"
        )
        for i, node in enumerate(result):
            assert node.a == f"a-{i}"
            assert node.b == f"b-{i}"
            assert node.c == f"c-{i}"

    async def test_resolve_overwriting_field_does_not_double_traverse(self):
        """When resolve_* populates a traversable field, the resolved children
        must be queued for traversal exactly once.

        With deferred setattr (pre-refactor) the existing-fields scan sees the
        pre-resolve (empty) value, so the dedup is implicit. With immediate
        setattr (post-refactor) the scan sees the new value — the resolver must
        skip resolve_*-populated fields via an explicit loaded_field_keys set.
        A regression here would run each child's post_* twice.
        """
        counter = {"n": 0}

        class Child(BaseModel):
            id: int
            marker: int = 0

            def post_marker(self):
                counter["n"] += 1
                return counter["n"]

        class Parent(BaseModel):
            children: list[Child] = []

            def resolve_children(self):
                return [Child(id=1), Child(id=2), Child(id=3)]

        result = await Resolver().resolve(Parent())

        assert len(result.children) == 3
        assert counter["n"] == 3, (
            f"post_marker ran {counter['n']} times, expected 3 "
            "(children queued for traversal more than once)"
        )


# ──────────────────────────────────────────────────────────
# Test: typing-shape compatibility for child traversal
#   Regression for issue #77 review: _get_traversable_fields
#   previously only recognized bare ``list[X]`` and bare ``X``,
#   silently skipping ``X | None``, ``Optional[X]``,
#   ``list[X] | None``, ``Annotated[X, ...]``.
# ──────────────────────────────────────────────────────────


class TestTypingShapeTraversal:
    """Verify pre-existing (populated) child DTOs are traversed regardless
    of how their annotation is spelled. The child's ``post_*`` must run."""

    async def test_pep604_optional_child_traverses(self):
        """``child: ChildDTO | None`` — PEP 604 union."""

        class ChildDTO(BaseModel):
            id: int
            name: str = ""
            derived: str = ""

            def post_derived(self):
                return f"d-{self.name}"

        class ParentDTO(BaseModel):
            id: int
            child: ChildDTO | None = None

        result = await Resolver().resolve(
            ParentDTO(id=1, child=ChildDTO(id=10, name="kid")),
        )
        assert result.child is not None
        assert result.child.derived == "d-kid"

    async def test_typing_optional_child_traverses(self):
        """``child: Optional[ChildDTO]`` — legacy typing.Optional."""

        class ChildDTO(BaseModel):
            id: int
            name: str = ""
            derived: str = ""

            def post_derived(self):
                return f"d-{self.name}"

        class ParentDTO(BaseModel):
            id: int
            child: ChildDTO | None = None

        result = await Resolver().resolve(
            ParentDTO(id=1, child=ChildDTO(id=10, name="kid")),
        )
        assert result.child is not None
        assert result.child.derived == "d-kid"

    async def test_annotated_child_traverses(self):
        """``child: Annotated[ChildDTO, ...]`` — Pydantic strips the
        Annotated wrapper at model creation, but the test guards against
        any future regression in _extract_dto_cls_and_cardinality."""

        class ChildDTO(BaseModel):
            id: int
            name: str = ""
            derived: str = ""

            def post_derived(self):
                return f"d-{self.name}"

        class ParentDTO(BaseModel):
            id: int
            child: Annotated[ChildDTO, "metadata"] = None

        result = await Resolver().resolve(
            ParentDTO(id=1, child=ChildDTO(id=10, name="kid")),
        )
        assert result.child is not None
        assert result.child.derived == "d-kid"

    async def test_list_optional_child_traverses(self):
        """``children: list[ChildDTO] | None`` — list-of-DTO wrapped in Optional."""

        class ChildDTO(BaseModel):
            id: int
            name: str = ""
            derived: str = ""

            def post_derived(self):
                return f"d-{self.name}"

        class ParentDTO(BaseModel):
            id: int
            children: list[ChildDTO] | None = None

        result = await Resolver().resolve(
            ParentDTO(
                id=1,
                children=[ChildDTO(id=10, name="a"), ChildDTO(id=11, name="b")],
            ),
        )
        assert result.children is not None
        assert [c.derived for c in result.children] == ["d-a", "d-b"]

    async def test_optional_child_none_not_traversed(self):
        """``child: ChildDTO | None`` with child=None must not crash and
        must leave child as None."""

        class ChildDTO(BaseModel):
            id: int
            derived: str = ""

            def post_derived(self):
                return f"d-{self.id}"

        class ParentDTO(BaseModel):
            id: int
            child: ChildDTO | None = None

        result = await Resolver().resolve(ParentDTO(id=1, child=None))
        assert result.child is None

    async def test_extract_dto_cls_and_cardinality_unit(self):
        """Direct unit checks on the helper used by traversal and auto-load."""

        class MyDTO(BaseModel):
            x: int

        assert Resolver._extract_dto_cls_and_cardinality(MyDTO) == (MyDTO, False)
        assert Resolver._extract_dto_cls_and_cardinality(MyDTO | None) == (MyDTO, False)
        assert Resolver._extract_dto_cls_and_cardinality(MyDTO | None) == (MyDTO, False)
        assert Resolver._extract_dto_cls_and_cardinality(list[MyDTO]) == (MyDTO, True)
        assert Resolver._extract_dto_cls_and_cardinality(list[MyDTO] | None) == (MyDTO, True)
        assert Resolver._extract_dto_cls_and_cardinality(Annotated[MyDTO, "x"]) == (MyDTO, False)
        assert Resolver._extract_dto_cls_and_cardinality(int) is None
        assert Resolver._extract_dto_cls_and_cardinality(int | None) is None
        assert Resolver._extract_dto_cls_and_cardinality("ForwardRef") is None
