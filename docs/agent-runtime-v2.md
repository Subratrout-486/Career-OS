# Career OS Agent Runtime v2

Career OS now has a provider-agnostic multi-agent runtime inspired by the architectural lessons of DeepSeek Harness. DeepSeek Harness is not a runtime dependency.

## Architecture

```text
User objective
    |
    v
CEO / Orchestrator
    |
    +--> Job Research Agent
    +--> Career Analyst
    +--> Resume Agent
    +--> Engineering Copilot
    +--> Application Agent
              |
              v
       ActionPolicy
              |
       approval if risky
              |
       ToolExecutionPipeline
              |
       execute -> verify -> audit
```

## Runtime guarantees

- Every agent run becomes a durable `TaskRecord`.
- Session and step boundaries are written to the existing audit store.
- Parent/child delegation is explicit through `parent_task_id` and `AgentMessage`.
- Agent capabilities and tools are registered through `AgentRegistry`.
- High-risk external actions fail closed when approval is unavailable.
- Approved high-risk actions are one-shot and cannot be replayed with the same approval.
- External actions require post-execution verification.
- Restart inspection is available through the existing `HarnessRecovery` mechanism.
- Providers are injected as executors; the runtime does not assume a specific model vendor.

## Agent roles

`ceo` coordinates and delegates. `job-research` handles research-oriented work. `career-analyst` handles matching and gap analysis. `resume-agent` handles ATS/resume work while preserving verified facts. `engineering-copilot` is the controlled coding/test/GitHub worker. `application-agent` handles application preparation and requires approval for submission.

## Important boundary

The current runtime supplies the execution seam and safety contracts. It does not pretend that a provider, browser, terminal, GitHub credential, or external model is available when it is not. Those integrations must be injected through approved adapters.

This keeps Career OS independent of DeepSeek Harness while allowing a future adapter for an actual agent backend, MCP/ACP worker, browser worker, or coding agent.
