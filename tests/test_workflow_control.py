from types import SimpleNamespace

import pytest

from career_os.workflow_control import register_control_handlers


def test_router_first_match_with_or_and_groups():
    engine = SimpleNamespace(handlers={})
    engine.register_handler = lambda kind, fn: engine.handlers.__setitem__(kind, fn)
    register_control_handlers(engine)
    handler = engine.handlers["ROUTER"]
    node = SimpleNamespace(config={
        "execution_type": "EXECUTE_FIRST_MATCH",
        "branches": [
            {"id": "high", "conditions": [[
                {"first_value": "{{ score }}", "operator": "NUMBER_IS_GREATER_THAN", "second_value": 90},
                {"first_value": "{{ verified }}", "operator": "BOOLEAN_IS_TRUE"},
            ]]},
            {"id": "normal", "conditions": [[
                {"first_value": "{{ score }}", "operator": "NUMBER_IS_GREATER_THAN", "second_value": 50},
            ]]},
        ],
    })
    result = handler(node=node, inputs={}, context={"score": 95, "verified": True}, run=None)
    assert result["branches"][0]["branch_id"] == "high"
    assert result["count"] == 1


def test_router_execute_all_matches():
    engine = SimpleNamespace(handlers={})
    engine.register_handler = lambda kind, fn: engine.handlers.__setitem__(kind, fn)
    register_control_handlers(engine)
    node = SimpleNamespace(config={
        "execution_type": "EXECUTE_ALL_MATCH",
        "branches": [
            {"id": "a", "conditions": [[{"first_value": "{{ status }}", "operator": "TEXT_EXACTLY_MATCHES", "second_value": "ready"}]]},
            {"id": "b", "conditions": [[{"first_value": "{{ score }}", "operator": "NUMBER_IS_GREATER_THAN", "second_value": 50}]]},
        ],
    })
    result = engine.handlers["ROUTER"](node=node, inputs={}, context={"status": "ready", "score": 80}, run=None)
    assert [b["branch_id"] for b in result["branches"]] == ["a", "b"]


def test_router_fallback_and_missing_value():
    engine = SimpleNamespace(handlers={})
    engine.register_handler = lambda kind, fn: engine.handlers.__setitem__(kind, fn)
    register_control_handlers(engine)
    node = SimpleNamespace(config={
        "execution_type": "EXECUTE_FIRST_MATCH",
        "branches": [{"id": "real", "conditions": [[{"first_value": "{{ missing }}", "operator": "EXISTS"}]]}],
        "fallback": {"id": "otherwise"},
    })
    result = engine.handlers["ROUTER"](node=node, inputs={}, context={}, run=None)
    assert result["branches"][0]["branch_id"] == "otherwise"


def test_router_rejects_unknown_operator():
    engine = SimpleNamespace(handlers={})
    engine.register_handler = lambda kind, fn: engine.handlers.__setitem__(kind, fn)
    register_control_handlers(engine)
    node = SimpleNamespace(config={
        "branches": [{"id": "bad", "conditions": [[{"first_value": 1, "operator": "NOPE", "second_value": 1}]]}],
    })
    with pytest.raises(ValueError, match="Unsupported ROUTER operator"):
        engine.handlers["ROUTER"](node=node, inputs={}, context={}, run=None)
