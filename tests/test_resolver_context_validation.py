"""Tests for Resolver context input validation.

Migrated from pydantic-resolve #291: ``Resolver(context=...)`` should reject
nonsensical inputs at __init__ rather than coercing them silently and
surfacing the failure later as an unrelated AttributeError / KeyError.

- ``None`` / omitted → valid (no context).
- non-empty ``dict`` → valid.
- empty ``dict`` → ``ValueError`` (almost always a bug).
- non-dict truthy value (``[1,2,3]``, ``42``, ``"str"``) → ``TypeError``.

Run::

    pytest tests/test_resolver_context_validation.py -v
"""
from __future__ import annotations

import pytest

from nexusx.resolver import Resolver


class TestContextValidation:
    def test_none_context_allowed(self):
        """Resolver() and Resolver(context=None) must both be valid."""
        assert Resolver()._context == {}
        assert Resolver(context=None)._context == {}

    def test_non_empty_dict_context_allowed(self):
        """A non-empty dict is the normal case."""
        r = Resolver(context={"user_id": 42})
        assert r._context == {"user_id": 42}

    def test_empty_dict_rejected(self):
        """Empty dict is almost always a bug — fail loud at construction."""
        with pytest.raises(ValueError, match="non-empty dict"):
            Resolver(context={})

    @pytest.mark.parametrize("bad", [[1, 2, 3], ("a", "b"), "string", 42, object()])
    def test_non_dict_rejected(self, bad):
        """Non-dict values must raise TypeError at __init__, not slip through
        to a confusing failure deep inside _traverse."""
        with pytest.raises(TypeError, match="context must be a dict"):
            Resolver(context=bad)
