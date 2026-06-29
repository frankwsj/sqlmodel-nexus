"""Tests for ``date`` and ``time`` argument handling in GraphQL.

Reproduces the bug discovered in the child-calendar project:

A SQLModel entity with a ``date`` or ``time`` field (e.g. ``date: date``,
``start_time: time``) currently round-trips through GraphQL as a **string**:

1. ``TypeConverter.SCALAR_TYPE_MAP`` only knows about ``datetime``. ``date`` and
   ``time`` fall through to the ``or "String"`` default in
   ``sdl_generator._python_type_to_graphql``, so the SDL emits ``String!``
   for fields that should be ``Date!`` / ``Time!``.

2. ``ArgumentBuilder._convert_scalar_value`` only special-cases ``datetime``.
   When a mutation is called with ``date: "2026-06-29"`` or
   ``start_time: "19:30"``, the string reaches the method unchanged. If the
   method then passes it straight to SQLModel (the common case), SQLite
   raises ``TypeError: SQLite Date type only accepts Python date objects``.

3. ``IntrospectionGenerator._build_scalar_types`` hard-codes the scalar list
   as ``["Int", "Float", "String", "Boolean", "ID", "DateTime"]`` — no
   ``Date`` or ``Time`` entries, so even if (1) is fixed GraphiQL won't
   advertise the new scalars.

These tests assert the **expected correct behaviour** (date/time reach the
method as ``datetime.date`` / ``datetime.time`` objects). They fail today;
the fix touches the three places above. Pattern mirrors
``test_argument_types.TestArgumentTypeInE2EQuery`` for the datetime case.
"""

from __future__ import annotations

from datetime import date, time

import pytest
from graphql import parse
from sqlmodel import Field, SQLModel

from nexusx.execution.argument_builder import ArgumentBuilder
from nexusx.introspection import IntrospectionGenerator
from nexusx.sdl_generator import SDLGenerator
from nexusx.type_converter import TypeConverter

# ── 1. TypeConverter scalar map ───────────────────────────────────────


class TestTypeConverterScalarMap:
    """``date`` and ``time`` should resolve to GraphQL ``Date`` / ``Time``."""

    def test_date_maps_to_date_scalar(self) -> None:
        converter = TypeConverter(entity_names=set())
        assert converter.get_scalar_type_name(date) == "Date"

    def test_time_maps_to_time_scalar(self) -> None:
        converter = TypeConverter(entity_names=set())
        assert converter.get_scalar_type_name(time) == "Time"

    def test_datetime_still_maps_to_datetime_scalar(self) -> None:
        """Regression guard: existing datetime mapping must keep working."""
        from datetime import datetime
        converter = TypeConverter(entity_names=set())
        assert converter.get_scalar_type_name(datetime) == "DateTime"


# ── 2. SDL generator emits Date!/Time! ────────────────────────────────


class _EventForSdl(SQLModel, table=False):
    """Stand-in entity with date/time fields (no table needed for SDL test)."""

    id: int | None = Field(default=None, primary_key=True)
    when: date = Field(description="event date")
    start_time: time = Field(description="start time")
    optional_when: date | None = Field(default=None, description="optional date")


class TestSDLDateAndTime:
    """SDL for date/time fields should emit ``Date`` / ``Time``, not ``String``."""

    def _generate(self) -> str:
        sdl = SDLGenerator([_EventForSdl], query_description=None, mutation_description=None)
        # SDLGenerator gets its own converter internally; pass via the public generate path.
        return sdl.generate(loader_registry=None)

    def test_date_field_emits_date_scalar(self) -> None:
        s = self._generate()
        # Currently emits `when: String!` — should emit `when: Date!`
        assert "when: Date!" in s, f"Expected `when: Date!` in SDL, got:\n{s}"

    def test_time_field_emits_time_scalar(self) -> None:
        s = self._generate()
        assert "start_time: Time!" in s, f"Expected `start_time: Time!` in SDL, got:\n{s}"

    def test_optional_date_emits_date_scalar(self) -> None:
        s = self._generate()
        # Optional fields render as bare `Type` (no `!`)
        assert "optional_when: Date" in s, f"Expected `optional_when: Date` in SDL, got:\n{s}"

    def test_string_does_not_appear_for_date_or_time_fields(self) -> None:
        """Sanity: the date/time fields must not fall back to String."""
        s = self._generate()
        assert "when: String" not in s
        assert "start_time: String" not in s


# ── 3. ArgumentBuilder converts date/time strings back to objects ─────


class TestArgumentBuilderDateAndTime:
    """When GraphQL sends a date/time literal, the method should receive
    a native ``datetime.date`` / ``datetime.time`` object, not a string.
    """

    def _build_args(
        self,
        query: str,
        hint_for: dict[str, type],
        variables: dict | None = None,
    ) -> dict:
        """Build a fake method whose signature carries the given type hints,
        then run ArgumentBuilder against the parsed query.
        """
        # Build a class with a method whose annotations match hint_for.
        # We use a fresh function each call so type hints stay isolated.
        annotations = {"return": type(None)}
        annotations.update(hint_for)
        params = ["cls"] + list(hint_for.keys())

        # Construct the function via exec so annotations land properly.
        ns: dict = {}
        func_src = (
            "async def get(cls, "
            + ", ".join(f"{p}: object" for p in params[1:])
            + "):\n    return None\n"
        )
        exec(func_src, ns)
        method = ns["get"]
        method.__annotations__ = dict(hint_for)

        class _Holder(SQLModel, table=False):
            pass

        document = parse(query)
        selection = document.definitions[0].selection_set.selections[0]
        builder = ArgumentBuilder()
        return builder.build_arguments(
            selection,
            variables,
            method,
            _Holder,
            set(),
        )

    def test_date_literal_reaches_method_as_date(self) -> None:
        args = self._build_args(
            '{ holderGet(when: "2026-06-29") { id } }',
            {"when": date},
        )
        assert args["when"] == date(2026, 6, 29)
        assert isinstance(args["when"], date)

    def test_time_literal_reaches_method_as_time(self) -> None:
        args = self._build_args(
            '{ holderGet(start_time: "19:30") { id } }',
            {"start_time": time},
        )
        assert args["start_time"] == time(19, 30)
        assert isinstance(args["start_time"], time)

    def test_time_literal_with_seconds_reaches_method_as_time(self) -> None:
        args = self._build_args(
            '{ holderGet(start_time: "19:30:45") { id } }',
            {"start_time": time},
        )
        assert args["start_time"] == time(19, 30, 45)

    def test_date_variable_reaches_method_as_date(self) -> None:
        args = self._build_args(
            "query($when: Date) { holderGet(when: $when) { id } }",
            {"when": date | None},
            variables={"when": "2026-06-29"},
        )
        assert args["when"] == date(2026, 6, 29)
        assert isinstance(args["when"], date)

    def test_time_variable_reaches_method_as_time(self) -> None:
        args = self._build_args(
            "query($t: Time) { holderGet(start_time: $t) { id } }",
            {"start_time": time | None},
            variables={"t": "19:30"},
        )
        assert args["start_time"] == time(19, 30)


# ── 4. Introspection lists Date / Time scalars ────────────────────────


class TestIntrospectionScalars:
    """GraphiQL introspection should advertise ``Date`` and ``Time`` scalars
    so clients know they exist. Currently only ``DateTime`` is listed.
    """

    def _scalar_names(self) -> set[str]:
        gen = IntrospectionGenerator(
            entities=[],
            query_methods={},
            mutation_methods={},
        )
        data = gen.generate()
        # introspection data shape: {"queryType":..., "types": [...], ...}
        # (NOT wrapped under "__schema" — that wrapper is added by callers)
        types = data.get("types", []) if isinstance(data, dict) else []
        return {t["name"] for t in types if t.get("kind") == "SCALAR"}

    def test_introspection_advertises_date_scalar(self) -> None:
        names = self._scalar_names()
        assert "Date" in names, f"Date scalar missing from introspection. Got: {sorted(names)}"

    def test_introspection_advertises_time_scalar(self) -> None:
        names = self._scalar_names()
        assert "Time" in names, f"Time scalar missing from introspection. Got: {sorted(names)}"

    def test_introspection_still_has_datetime_scalar(self) -> None:
        """Regression guard."""
        names = self._scalar_names()
        assert "DateTime" in names


# ── 5. E2E: mutation persists date/time to SQLite without TypeError ──


class _EvtRowForE2E(SQLModel, table=True):
    """Module-level table so the test_db fixture's ``create_all`` picks it up."""

    __tablename__ = "_evt_row_dt_e2e"
    id: int | None = Field(default=None, primary_key=True)
    when: date = Field()
    start_time: time = Field()


@pytest.mark.usefixtures("test_db")
async def test_mutation_with_date_and_time_persists_to_db():
    """A SQLModel with ``date`` / ``time`` columns, mutated via GraphQL with
    string literals, must persist without raising ``TypeError: SQLite Date
    type only accepts Python date objects as input``.

    Currently fails because the string reaches the method untouched.

    Mirrors the real-world surface from child-calendar: the framework's
    ArgumentBuilder receives a parsed GraphQL string and must hand the method
    a Python ``date`` / ``time`` object. We exercise the same path by routing
    a parsed mutation through ``ArgumentBuilder.build_arguments`` and then
    invoking the method with the resulting kwargs.
    """
    from graphql import parse
    from sqlmodel import select

    from nexusx.execution.argument_builder import ArgumentBuilder
    from tests.conftest import get_test_session_factory

    received: dict = {}

    async def create_event(when: date, start_time: time) -> _EvtRowForE2E:
        received["when"] = when
        received["start_time"] = start_time
        sf = get_test_session_factory()
        async with sf() as session:
            row = _EvtRowForE2E(when=when, start_time=start_time)
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    # Set annotations so ArgumentBuilder can resolve type hints.
    create_event.__annotations__ = {"when": date, "start_time": time, "return": _EvtRowForE2E}

    # Parse a mutation-shaped query and route through ArgumentBuilder.
    document = parse(
        'mutation { createEvent(when: "2026-06-29", start_time: "19:30") { id } }'
    )
    selection = document.definitions[0].selection_set.selections[0]
    builder = ArgumentBuilder()
    args = builder.build_arguments(selection, None, create_event, _EvtRowForE2E, set())

    # The builder must hand us native date/time, not strings.
    assert isinstance(args.get("when"), date), (
        f"ArgumentBuilder returned when as {type(args.get('when')).__name__}, expected date"
    )
    assert isinstance(args.get("start_time"), time), (
        f"ArgumentBuilder returned start_time as "
        f"{type(args.get('start_time')).__name__}, expected time"
    )

    # And the insert must actually succeed (no SQLite TypeError).
    await create_event(**args)

    sf = get_test_session_factory()
    async with sf() as session:
        rows = list((await session.exec(select(_EvtRowForE2E))).all())
    assert len(rows) == 1
    assert rows[0].when == date(2026, 6, 29)
    assert rows[0].start_time == time(19, 30)
