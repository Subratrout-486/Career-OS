from __future__ import annotations

import asyncio

from career_os.model_executor import NoModelConfigured, UnconfiguredModelExecutor


def test_harness_can_exist_without_a_model_executor():
    executor = UnconfiguredModelExecutor()
    try:
        asyncio.run(executor.generate(system="test", user="test"))
    except NoModelConfigured as exc:
        assert "model reasoning requires an injected executor" in str(exc)
    else:
        raise AssertionError("unconfigured model executor must fail closed")
