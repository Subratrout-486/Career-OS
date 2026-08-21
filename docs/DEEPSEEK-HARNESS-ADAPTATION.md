# DeepSeek-inspired Career OS runtime

Career OS uses a small runtime layer inspired by the architectural ideas reviewed in DeepSeek Harness. This is an adaptation, not a vendored copy or dependency.

## Implemented

- **Session/step lifecycle:** `AgentHarness` records session, step, model-request, tool-call, tool-result, and completion events.
- **Durable checkpoints:** checkpoints are persisted into the existing `ControlPlaneStore` task payload before model/tool boundaries.
- **Composable agent registry:** `MultiAgentRuntime` registers specialist agents with explicit capabilities and tools instead of encoding every specialist as a separate GitHub Actions job.
- **Real provider execution:** when Conductor is configured, the registered Career Fit, Resume, and Recruiter Challenger agents execute through the configured Conductor runtime.
- **Bounded retry:** real specialist execution now retries the same durable child task up to its configured retry budget. Retries do not switch silently to another provider.
- **Fail-closed action policy:** high-risk actions such as `SUBMIT_APPLICATION` require explicit approval; an unavailable approval service blocks the action.
- **One-shot approval consumption:** consumed approval IDs are persisted on the task, preventing replay after a restart.
- **Tool execution pipeline:** policy → execution → post-execution verification → audit.
- **Recovery inspection:** `HarnessRecovery` identifies running/waiting/retrying tasks and distinguishes ordinary resume from possible external-side-effect reconciliation.

## Intentionally not copied

Career OS does not depend on DeepSeek Harness or replace its existing control plane. The existing `ControlPlaneStore`, task records, agent/model registry, browser execution safety, Notion integration, and Career OS pipeline remain the system of record and domain-specific execution layers.

## Runtime rule

A model may propose an action, but it does not directly authorize a high-risk external side effect.

```text
objective
    -> durable parent task
    -> specialist child task
    -> checkpoint
    -> configured provider execution
    -> retry same child when transiently failed
    -> verify / deterministic guard
    -> durable result + audit
```

If approval or verification is unavailable, Career OS must fail closed rather than claim success.

## Recovery rule

A task that was persisted as `TOOL_CALLING` before a process restart must be reconciled before replay. This avoids blindly repeating an external side effect such as an application submission.

## Current integration boundary

`ControlledCareerPipeline` creates the durable pipeline task and delegates AI-capable stages through `MultiAgentRuntime`. GitHub Actions remains the scheduler/trigger and artifact surface; it is not the AI agent runtime. Conductor remains the provider/orchestration boundary and selects the actual model/provider inside its connected environment.
