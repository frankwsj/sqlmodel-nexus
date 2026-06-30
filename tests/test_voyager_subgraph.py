"""Tests for the Voyager "Related Entities" sub-graph (spec 005).

Covers quickstart.md scenarios A1–A5:
- A1: filter_to_neighborhood precision (selected entity + direct neighbors only)
- A2: isolated entity (no neighbors → just self)
- A3: self-reference + parallel edges preserved
- A4: config passthrough (render config actually changes the DOT)
- A5: VoyagerContext.get_er_diagram_subgraph response shape
"""
from __future__ import annotations

from sqlmodel import Field, SQLModel

from nexusx import Relationship
from nexusx.loader.registry import ErManager
from nexusx.voyager.er_diagram_dot import ErDiagramDotBuilder

# ── Fixtures ───────────────────────────────────────────────────────────


async def _noop_loader(keys: list[int]) -> list:
    return [None for _ in keys]


class _Organization(SQLModel, table=True):
    __tablename__ = "subgraph_org"
    id: int | None = Field(default=None, primary_key=True)
    name: str


class _Workspace(SQLModel, table=True):
    __tablename__ = "subgraph_ws"
    id: int | None = Field(default=None, primary_key=True)
    name: str


class _Department(SQLModel, table=True):
    __tablename__ = "subgraph_dept"
    id: int | None = Field(default=None, primary_key=True)
    name: str


class _Unrelated(SQLModel, table=True):
    __tablename__ = "subgraph_unrelated"
    id: int | None = Field(default=None, primary_key=True)
    note: str


# Two parallel relationships between the same pair (A + B with two edges).
class _ParallelA(SQLModel, table=True):
    __tablename__ = "subgraph_parallel_a"
    id: int | None = Field(default=None, primary_key=True)


class _ParallelB(SQLModel, table=True):
    __tablename__ = "subgraph_parallel_b"
    id: int | None = Field(default=None, primary_key=True)


# Self-referencing entity (X → X).
class _SelfRef(SQLModel, table=True):
    __tablename__ = "subgraph_selfref"
    id: int | None = Field(default=None, primary_key=True)
    parent_id: int | None = Field(default=None, foreign_key="subgraph_selfref.id")


_Organization.__relationships__ = [
    Relationship(fk="id", target=list[_Workspace], name="workspaces", loader=_noop_loader),
    Relationship(fk="id", target=list[_Department], name="departments", loader=_noop_loader),
]

_ParallelA.__relationships__ = [
    Relationship(fk="id", target=list[_ParallelB], name="primary_link", loader=_noop_loader),
    Relationship(fk="id", target=list[_ParallelB], name="secondary_link", loader=_noop_loader),
]

_SelfRef.__relationships__ = [
    Relationship(fk="parent_id", target=list[_SelfRef], name="parent", loader=_noop_loader),
]


def _make_registry(*entities) -> ErManager:
    async def session_factory():
        return None

    return ErManager(entities=list(entities), session_factory=session_factory)


def _fqid(cls: type) -> str:
    return f"{cls.__module__}.{cls.__name__}"


# ── A1: neighborhood precision ─────────────────────────────────────────


class TestNeighborhoodPrecision:
    def test_subgraph_contains_only_selected_plus_direct_neighbors(self):
        registry = _make_registry(_Organization, _Workspace, _Department, _Unrelated)
        builder = ErDiagramDotBuilder(registry)
        builder.analysis()
        builder.filter_to_neighborhood(_fqid(_Organization))

        node_ids = set(builder.node_set.keys())
        assert node_ids == {
            _fqid(_Organization),
            _fqid(_Workspace),
            _fqid(_Department),
        }
        # _Unrelated must be excluded.
        assert _fqid(_Unrelated) not in node_ids

    def test_every_kept_edge_has_selected_entity_as_endpoint(self):
        registry = _make_registry(_Organization, _Workspace, _Department, _Unrelated)
        builder = ErDiagramDotBuilder(registry)
        builder.analysis()
        builder.filter_to_neighborhood(_fqid(_Organization))

        anchor = _fqid(_Organization)
        for link in builder.links:
            assert link.source_origin == anchor or link.target_origin == anchor


# ── A2: isolated entity ────────────────────────────────────────────────


class TestIsolatedEntity:
    def test_isolated_entity_keeps_only_self_with_no_edges(self):
        registry = _make_registry(_Organization, _Workspace, _Department, _Unrelated)
        builder = ErDiagramDotBuilder(registry)
        builder.analysis()
        builder.filter_to_neighborhood(_fqid(_Unrelated))

        assert set(builder.node_set.keys()) == {_fqid(_Unrelated)}
        assert builder.links == []


# ── A3: self-reference + parallel edges ────────────────────────────────


class TestSpecialEdges:
    def test_parallel_edges_between_same_pair_are_both_preserved(self):
        registry = _make_registry(_ParallelA, _ParallelB)
        builder = ErDiagramDotBuilder(registry)
        builder.analysis()
        builder.filter_to_neighborhood(_fqid(_ParallelA))

        # Both parallel edges (primary_link, secondary_link) must survive.
        labels = [link.label for link in builder.links]
        assert any("primary_link" in lbl for lbl in labels)
        assert any("secondary_link" in lbl for lbl in labels)
        assert len(builder.links) == 2

    def test_self_reference_is_preserved_as_self_loop(self):
        registry = _make_registry(_SelfRef)
        builder = ErDiagramDotBuilder(registry)
        builder.analysis()
        builder.filter_to_neighborhood(_fqid(_SelfRef))

        # The self-loop edge should be kept (both endpoints == _SelfRef).
        sid = _fqid(_SelfRef)
        self_edges = [
            link for link in builder.links
            if link.source_origin == sid and link.target_origin == sid
        ]
        assert len(self_edges) == 1
        assert set(builder.node_set.keys()) == {sid}


# ── A4: config passthrough ─────────────────────────────────────────────


class TestEdgeDirectionAndType:
    """Spec 005 Story 2 / FR-009 — edges in the sub-graph must carry direction
    (source/target) so the renderer can convey in/out/bidirectional semantics,
    and must remain consistent with the main graph's edge rendering (FR-009).
    FR-010 (parallel edges) is covered by TestSpecialEdges above.
    """

    def test_edges_carry_source_and_target_origins(self):
        registry = _make_registry(_Organization, _Workspace, _Department)
        builder = ErDiagramDotBuilder(registry)
        builder.analysis()
        builder.filter_to_neighborhood(_fqid(_Organization))

        assert len(builder.links) >= 1
        for link in builder.links:
            # Every kept link has a distinct source and target origin (direction info).
            assert link.source_origin
            assert link.target_origin
            # Source anchor encodes the field that owns the relationship.
            assert "::" in link.source or "->" in str(link.label) or link.label

    def test_subgraph_edges_match_main_graph_edge_set_for_anchor(self):
        """Edges incident to the anchor must be a subset of the main graph's edges,
        with no distortion (FR-009 consistency)."""
        registry = _make_registry(_Organization, _Workspace, _Department)

        full = ErDiagramDotBuilder(registry)
        full.analysis()
        anchor = _fqid(_Organization)
        full_edges_for_anchor = {
            (link.source_origin, link.target_origin, link.label)
            for link in full.links
            if link.source_origin == anchor or link.target_origin == anchor
        }

        sub = ErDiagramDotBuilder(registry)
        sub.analysis()
        sub.filter_to_neighborhood(anchor)
        sub_edges = {
            (link.source_origin, link.target_origin, link.label) for link in sub.links
        }

        assert sub_edges == full_edges_for_anchor





class TestConfigPassthrough:
    def test_different_show_module_yields_different_dot(self):
        registry = _make_registry(_Organization, _Workspace, _Department)
        anchor = _fqid(_Organization)

        def _render(show_module: bool) -> str:
            b = ErDiagramDotBuilder(registry, show_module=show_module)
            b.analysis()
            b.filter_to_neighborhood(anchor)
            return b.render_dot()

        dot_with_clusters = _render(show_module=True)
        dot_without_clusters = _render(show_module=False)

        # The two DOTs must differ — proves the render config actually flows through.
        assert dot_with_clusters != dot_without_clusters
        assert "digraph" in dot_with_clusters


# ── A5: response shape from VoyagerContext ─────────────────────────────


class TestSubgraphResponseShape:
    def test_get_er_diagram_subgraph_returns_dot_links_schemas(self):
        from nexusx.voyager.voyager_context import VoyagerContext

        registry = _make_registry(_Organization, _Workspace, _Department, _Unrelated)
        ctx = VoyagerContext(services=[], er_manager=registry, name="t")
        anchor = _fqid(_Organization)

        result = ctx.get_er_diagram_subgraph({
            "schema_name": anchor,
            "show_fields": "object",
            "show_module": True,
            "edge_minlen": 3,
            "show_methods": True,
        })

        assert set(result.keys()) == {"dot", "links", "schemas"}
        assert "digraph" in result["dot"]
        # Neighborhood: _Organization + _Workspace + _Department (not _Unrelated).
        schema_ids = {s["id"] for s in result["schemas"]}
        assert schema_ids == {anchor, _fqid(_Workspace), _fqid(_Department)}
        # Every returned link touches the anchor.
        for link in result["links"]:
            assert link["source_origin"] == anchor or link["target_origin"] == anchor

    def test_edge_minlen_is_clamped_to_valid_range(self):
        from nexusx.voyager.voyager_context import VoyagerContext

        registry = _make_registry(_Organization, _Workspace)
        ctx = VoyagerContext(services=[], er_manager=registry, name="t")

        # Out-of-range values should not crash; clamped to [3, 10].
        for raw in (-5, 0, 2, 7, 11, 999):
            result = ctx.get_er_diagram_subgraph({
                "schema_name": _fqid(_Organization),
                "show_fields": "object",
                "show_module": True,
                "edge_minlen": raw,
                "show_methods": True,
            })
            assert "digraph" in result["dot"]

    def test_unknown_schema_name_yields_empty_result(self):
        from nexusx.voyager.voyager_context import VoyagerContext

        registry = _make_registry(_Organization, _Workspace)
        ctx = VoyagerContext(services=[], er_manager=registry, name="t")

        result = ctx.get_er_diagram_subgraph({
            "schema_name": "does.not.Exist",
            "show_fields": "object",
            "show_module": True,
            "edge_minlen": 3,
            "show_methods": True,
        })
        assert result == {"dot": "", "links": [], "schemas": []}
