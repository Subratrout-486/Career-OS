# DeepSeek-inspired Career OS runtime

Career OS now has a small runtime layer inspired by the architectural ideas we reviewed in DeepSeek Harness. This is an adaptation, not a vendored copy or dependency.

## Implemented

- **Session/step lifecycle:** `AgentHarness` records session, step, model-request, tool-call, tool-result, and completion events.
- **Durable checkpoints:** checkpoints are persisted into the existing `ControlPlaneStore` task payload before model/tool boundaries.
- **Fail-closed action policy:** high-risk actions such as `SUBMIT_APPLICATION` require explicit approval; an unavailable approval service blocks the action.
- **One-shot approval consumption:** consumed approval IDs are persisted on the task, preventing replay after a restart.
- **Tool execution pipeline:** policy → execution → post-execution verification → audit.
- **Recovery inspection:** `HarnessRecovery` identifies running/waiting/retrying tasks and distinguishes ordinary resume from possible external-side-effect reconciliation.

## Intentionally not copied

Career OS does not depend on DeepSeek Harness or replace its existing control plane. The existing `ControlPlaneStore`, task records, agent/model registry, browser execution safety, Notion integration, and Career OS pipeline remain the system of record and domain-specific execution layers.

## Runtime rule

A model may propose an action, but it does not directly authorize a high-risk external side effect.

```text
model proposal
    -> checkpoint
    -> policy
    -> approval when required
    -> execute
    -> verify
    -> durable audit
```

If approval or verification is unavailable, Career OS must fail closed rather than claim success.

## Recovery rule

A task that was persisted as `TOOL_CALLING` before a process restart must be reconciled before replay. This avoids blindly repeating an external side effect such as an application submission.

## Next integration step

Wire `AgentHarness` into the existing `PlatformOrchestrator` and browser/application execution paths, then add a production restart/reconciliation test. This branch deliberately does not change existing application behavior until those integration tests pass.
