# Agent Hub → Conductor Runtime

## Canonical execution path

Career OS should use one production AI execution path:

`Career OS → Agent Command Hub → ConductorRuntime → Conductor MCP → AgentFlow/Conductor → structured result → Career OS control plane`

The Agent Command Hub is the routing/control layer. It must not introduce a second provider-specific execution API.

## Runtime contract

`ConductorRuntime` is the canonical provider-neutral runtime. It submits durable objectives through the existing Conductor MCP tools and polls the run until a terminal result is available.

The Agent Hub should resolve an agent and command first, then translate the command into a Conductor workflow/objective through this runtime.

## Rules

- Do not add model-provider API keys to Career OS.
- Do not use `CONDUCTOR_DISPATCH_URL` as a second production execution path.
- Direct-provider runtimes may exist only as isolated tests/development harnesses and must not be selected by the production Agent Hub.
- Browser/application submission remains behind the existing approval and execution gates.
- Agent results must be persisted through the existing task/control-plane contracts.

## First smoke test

Use a harmless `analyze_jd` task. Verify:

1. Agent Hub resolves `analyze_jd`.
2. A durable task/message is created.
3. ConductorRuntime submits a Conductor objective.
4. A Conductor run ID is returned.
5. The run reaches a terminal state.
6. Structured output is returned to Career OS.
7. No browser execution or application submission occurs.
