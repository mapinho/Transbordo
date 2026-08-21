"""
M11: Optional-with-None-default parameters in ai_assistant.py / mcp_server.py
tool-wrapper functions were annotated with bare types (e.g. `start_date: str
= None`) instead of `Optional[str]`. This violates PEP 484 and can cause
JSON-schema generation for Gemini function-calling / MCP tool discovery to
misrepresent these parameters as required/non-nullable.

This is a pure type-annotation fix with no runtime behavior change (Python
does not enforce annotations at call time), following the same documented
exception pattern used for the Mapped[] typing fix in models.py (A11/L4):

1. A genuine red/green test via `inspect.signature()` -- this DOES
   distinguish before/after, since the annotation object itself changes from
   the bare class (e.g. `str`) to `typing.Optional[str]`
   (== `typing.Union[str, None]`).
2. A behavior-preservation test confirming the wrapper functions still work
   identically (both with the parameter omitted and with an explicit
   non-None value) after the annotation change.
"""
import inspect
import typing

import pytest

import ai_assistant
import mcp_server


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_optional(annotation) -> bool:
    """True if `annotation` is `typing.Optional[X]` (i.e. `typing.Union[X,
    None]`), as opposed to a bare type like `str` or `int`."""
    return (
        typing.get_origin(annotation) is typing.Union
        and type(None) in typing.get_args(annotation)
    )


# Every (module, function_name, [param_names_with_None_default]) combo that
# M11 must fix in both files.
AFFECTED = [
    (ai_assistant, "get_daily_movements", ["start_date", "end_date", "origin_id", "destination_id"]),
    (ai_assistant, "get_monthly_summary", ["start_date", "end_date"]),
    (mcp_server, "get_daily_movements", ["start_date", "end_date", "origin_id", "destination_id"]),
    (mcp_server, "get_monthly_summary", ["start_date", "end_date"]),
]

# Params that keep a real (non-None) default and must NOT be touched by M11.
UNCHANGED_DEFAULTS = [
    (ai_assistant, "get_daily_movements", "limit", 150),
    (mcp_server, "get_daily_movements", "limit", 150),
]


# ---------------------------------------------------------------------------
# 1) Genuine red/green static check via inspect.signature()
#    (fails against the pre-M11 code, passes after the fix)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("module,func_name,param_names", AFFECTED)
def test_none_default_params_are_annotated_optional(module, func_name, param_names):
    func = getattr(module, func_name)
    sig = inspect.signature(func)

    for name in param_names:
        param = sig.parameters[name]
        assert param.default is None, (
            f"{module.__name__}.{func_name}({name}) was expected to default to None"
        )
        assert _is_optional(param.annotation), (
            f"{module.__name__}.{func_name}({name}) annotation is "
            f"{param.annotation!r}, expected typing.Optional[...] "
            f"(a bare type with a None default violates PEP 484 -- M11)"
        )
        # The bare, un-parameterized type must not itself be the annotation.
        assert param.annotation not in (str, int, float, bool), (
            f"{module.__name__}.{func_name}({name}) is still annotated with "
            f"the bare type {param.annotation!r} instead of Optional[...]"
        )


@pytest.mark.parametrize("module,func_name,param_name,expected_default", UNCHANGED_DEFAULTS)
def test_real_default_params_are_left_untouched(module, func_name, param_name, expected_default):
    """M11 must only touch params whose default is None -- `limit: int =
    150` (a real, non-None default) must remain a bare `int`, not become
    Optional[int]."""
    func = getattr(module, func_name)
    sig = inspect.signature(func)
    param = sig.parameters[param_name]

    assert param.default == expected_default
    assert param.annotation is int
    assert not _is_optional(param.annotation)


# ---------------------------------------------------------------------------
# 2) Behavior preservation: calling with the param omitted (None default)
#    and with an explicit non-None value must both still work identically.
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_logistics(monkeypatch):
    """Replace logistics_services.get_daily_movements /
    get_monthly_summary with fakes that just echo back the kwargs they
    received, so we can assert the wrapper forwards args unchanged
    regardless of the annotation style used."""
    calls = {}

    def fake_get_daily_movements(**kwargs):
        calls["get_daily_movements"] = kwargs
        return [{"echo": kwargs}]

    def fake_get_monthly_summary(**kwargs):
        calls["get_monthly_summary"] = kwargs
        return {"echo": kwargs}

    monkeypatch.setattr(ai_assistant.logistics_services, "get_daily_movements", fake_get_daily_movements)
    monkeypatch.setattr(ai_assistant.logistics_services, "get_monthly_summary", fake_get_monthly_summary)
    monkeypatch.setattr(mcp_server.logistics_services, "get_daily_movements", fake_get_daily_movements)
    monkeypatch.setattr(mcp_server.logistics_services, "get_monthly_summary", fake_get_monthly_summary)

    return calls


@pytest.mark.parametrize("module", [ai_assistant, mcp_server])
def test_get_daily_movements_works_with_omitted_optional_params(module, fake_logistics):
    result = module.get_daily_movements(scenario_id=1)

    assert result == [{"echo": {
        "scenario_id": 1,
        "start_date": None,
        "end_date": None,
        "origin_id": None,
        "destination_id": None,
        "limit": 150,
    }}]


@pytest.mark.parametrize("module", [ai_assistant, mcp_server])
def test_get_daily_movements_works_with_explicit_values(module, fake_logistics):
    result = module.get_daily_movements(
        scenario_id=1,
        start_date="2026-01-01",
        end_date="2026-01-31",
        origin_id=10,
        destination_id=20,
        limit=50,
    )

    assert result == [{"echo": {
        "scenario_id": 1,
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
        "origin_id": 10,
        "destination_id": 20,
        "limit": 50,
    }}]


@pytest.mark.parametrize("module", [ai_assistant, mcp_server])
def test_get_monthly_summary_works_with_omitted_optional_params(module, fake_logistics):
    result = module.get_monthly_summary(scenario_id=1)

    assert result == {"echo": {
        "scenario_id": 1,
        "start_date": None,
        "end_date": None,
    }}


@pytest.mark.parametrize("module", [ai_assistant, mcp_server])
def test_get_monthly_summary_works_with_explicit_values(module, fake_logistics):
    result = module.get_monthly_summary(
        scenario_id=1,
        start_date="2026-01-01",
        end_date="2026-01-31",
    )

    assert result == {"echo": {
        "scenario_id": 1,
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
    }}
