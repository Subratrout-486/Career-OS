"""Generic AgentFlow control-flow primitives.

The router follows the useful Activepieces semantics: conditions are OR groups
of AND predicates, and execution can be FIRST_MATCH or ALL_MATCH. The module
is intentionally independent of Career OS so it can be registered by any
AgentFlow runtime.
"""
from __future__ import annotations

import re
from typing import Any


_MISSING = object()


def register_control_handlers(engine: Any) -> None:
    engine.register_handler("ROUTER", router_handler)


def router_handler(*, node: Any, inputs: dict[str, Any], context: dict[str, Any], run: Any) -> dict[str, Any]:
    config = dict(getattr(node, "config", {}) or {})
    execution_type = str(config.get("execution_type", "EXECUTE_FIRST_MATCH")).upper()
    if execution_type not in {"EXECUTE_FIRST_MATCH", "EXECUTE_ALL_MATCH"}:
        raise ValueError("ROUTER execution_type must be EXECUTE_FIRST_MATCH or EXECUTE_ALL_MATCH")

    branches = config.get("branches", [])
    if not isinstance(branches, list) or not branches:
        raise ValueError("ROUTER requires a non-empty config.branches list")

    matches: list[dict[str, Any]] = []
    for index, branch in enumerate(branches):
        if not isinstance(branch, dict):
            raise ValueError("Each ROUTER branch must be an object")
        conditions = branch.get("conditions", [])
        matched = _evaluate_groups(conditions, context, inputs)
        if not conditions and branch.get("otherwise", False):
            matched = True
        if matched:
            matches.append({
                "branch_index": index,
                "branch_id": branch.get("id", f"branch-{index}"),
                "name": branch.get("name", f"Branch {index + 1}"),
            })
            if execution_type == "EXECUTE_FIRST_MATCH":
                break

    if not matches:
        fallback = config.get("fallback")
        if fallback is not None:
            matches.append({
                "branch_index": len(branches),
                "branch_id": str(fallback.get("id", "otherwise")) if isinstance(fallback, dict) else "otherwise",
                "name": str(fallback.get("name", "Otherwise")) if isinstance(fallback, dict) else "Otherwise",
            })

    return {
        "execution_type": execution_type,
        "matched": bool(matches),
        "branches": matches,
        "count": len(matches),
    }


def _evaluate_groups(groups: Any, context: dict[str, Any], inputs: dict[str, Any]) -> bool:
    # Activepieces-style condition shape: outer list is OR, inner list is AND.
    if groups is None:
        return False
    if not isinstance(groups, list):
        raise ValueError("ROUTER conditions must be a list of condition groups")
    if not groups:
        return False
    values = {**context, **inputs}
    for group in groups:
        if not isinstance(group, list):
            raise ValueError("Each ROUTER condition group must be a list")
        if all(_evaluate_condition(condition, values) for condition in group):
            return True
    return False


def _evaluate_condition(condition: Any, values: dict[str, Any]) -> bool:
    if not isinstance(condition, dict):
        raise ValueError("ROUTER conditions must be objects")
    left = _resolve(condition.get("first_value"), values)
    operator = str(condition.get("operator", "EXISTS")).upper()
    right = _resolve(condition.get("second_value"), values)
    case_sensitive = bool(condition.get("case_sensitive", False))

    if operator == "EXISTS":
        return left is not _MISSING and left is not None
    if operator == "DOES_NOT_EXIST":
        return left is _MISSING or left is None
    if operator == "BOOLEAN_IS_TRUE":
        return left is True
    if operator == "BOOLEAN_IS_FALSE":
        return left is False

    if left is _MISSING:
        return False
    if operator == "TEXT_EXACTLY_MATCHES":
        a, b = str(left), str(right)
        return a == b if case_sensitive else a.casefold() == b.casefold()
    if operator == "TEXT_CONTAINS":
        a, b = str(left), str(right)
        return b in a if case_sensitive else b.casefold() in a.casefold()
    if operator == "TEXT_STARTS_WITH":
        a, b = str(left), str(right)
        return a.startswith(b) if case_sensitive else a.casefold().startswith(b.casefold())
    if operator == "TEXT_ENDS_WITH":
        a, b = str(left), str(right)
        return a.endswith(b) if case_sensitive else a.casefold().endswith(b.casefold())
    if operator == "TEXT_MATCHES_REGEX":
        flags = 0 if case_sensitive else re.IGNORECASE
        return re.search(str(right), str(left), flags) is not None

    if operator in {"NUMBER_IS_GREATER_THAN", "NUMBER_IS_GREATER_THAN_OR_EQUAL_TO", "NUMBER_IS_LESS_THAN", "NUMBER_IS_LESS_THAN_OR_EQUAL_TO", "NUMBER_IS_EQUAL_TO"}:
        try:
            a, b = float(left), float(right)
        except (TypeError, ValueError):
            return False
        return {
            "NUMBER_IS_GREATER_THAN": a > b,
            "NUMBER_IS_GREATER_THAN_OR_EQUAL_TO": a >= b,
            "NUMBER_IS_LESS_THAN": a < b,
            "NUMBER_IS_LESS_THAN_OR_EQUAL_TO": a <= b,
            "NUMBER_IS_EQUAL_TO": a == b,
        }[operator]

    raise ValueError(f"Unsupported ROUTER operator: {operator}")


def _resolve(value: Any, values: dict[str, Any]) -> Any:
    if not isinstance(value, str) or not value.startswith("{{") or not value.endswith("}}"):
        return value
    path = value[2:-2].strip()
    current: Any = values
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return _MISSING
    return current
