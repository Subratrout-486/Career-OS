from __future__ import annotations

import asyncio

import pytest

from career_os.conductor_runtime import ConductorRuntime, ConductorRuntimeError
from career_os.models import FitReport


def test_conductor_runtime_requires_server_side_bridge_config(monkeypatch):
    monkeypatch.delenv("CONDUCTOR_MCP_URL", raising=False)
    monkeypatch.delenv("CONDUCTOR_BASE_URL", raising=False)
    monkeypatch.delenv("CONDUCTOR_BRIDGE_TOKEN", raising=False)
    runtime = ConductorRuntime()
    with pytest.raises(ConductorRuntimeError, match="CONDUCTOR_MCP_URL"):
        asyncio.run(runtime.health())


def test_conductor_runtime_parses_fit_output():
    runtime = ConductorRuntime()
    value = runtime._parse_json_output('{"fit_score": 88, "recommendation": "APPLY"}')
    assert value["fit_score"] == 88
    assert value["recommendation"] == "APPLY"


def test_conductor_runtime_rejects_non_object_output():
    runtime = ConductorRuntime()
    with pytest.raises(ConductorRuntimeError):
        runtime._parse_json_output("[]")


def test_conductor_runtime_retries_structured_validation(monkeypatch):
    runtime = ConductorRuntime()
    calls = []

    async def fake_execute(*, objective, workflow):
        calls.append(workflow)
        if len(calls) == 1:
            return {"run_id": "run-1", "output": "not-json"}
        return {"run_id": "run-2", "output": '{"fit_score": 91, "recommendation": "APPLY", "band": "A"}'}

    monkeypatch.setattr(runtime, "_execute", fake_execute)
    result = asyncio.run(runtime._structured(workflow="CAREER_OS_FIT", objective="fit", model_cls=FitReport))
    assert result.fit_score == 91
    assert calls == ["CAREER_OS_FIT", "CAREER_OS_FIT"]
