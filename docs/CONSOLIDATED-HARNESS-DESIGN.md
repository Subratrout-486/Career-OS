# Consolidated Career OS Harness Design

## Decision

`AgentRuntime` remains the provider/model adapter and structured-domain runtime. `MultiAgentRuntime` becomes the single provider-agnostic harness facade over that runtime and the existing `ControlPlaneStore`. `AgentHarness`, `ActionPolicy`, and `ToolExecutionPipeline` remain implementation components of that facade rather than a second business runtime.

The existing `CareerOS.process` pipeline remains the domain engine. `ControlledCareerPipeline` creates one shared `AgentRuntime` and `MultiAgentRuntime`, injects the provider runtime into `CareerOS`, and wraps the real pipeline execution with durable session/step lifecycle events and checkpoints. The Conductor API remains review-only.

## Capability seams

| Capability | Consolidated owner | Existing policy preserved |
| --- | --- | --- |
| Provider/model registry | `AgentRuntime` provider adapters plus `ControlPlaneStore` model registry | Unconfigured providers are unavailable; fallback remains explicit |
| Agent/tool/skill registry | `AgentRegistry` and `AgentSpec` | Tools are declarative and external actions still pass policy |
| Sessions and durable steps | `MultiAgentRuntime` + `AgentHarness` | Existing JSON control-plane persistence |
| Planning and delegation | `MultiAgentRuntime` | Parent/child tasks and messages remain durable |
| Workflows/loops | Existing Career OS pipeline stages and browser lifecycle | No second workflow engine |
| Recovery/resume | `HarnessRecovery` plus browser execution state store | Reconcile `TOOL_CALLING`; do not replay blindly |
| External tools | `ToolExecutionPipeline` | Fail-closed high-risk approval and verification |
| Audit | `ControlPlaneStore` audit events | No prompt, credential, or sensitive content leakage added |
| Human takeover | Approval records and browser owner-only boundary | No automatic login/MFA/CAPTCHA/authorization bypass |

## Integration rule

Real specialist operations are registered as runtime-backed executors and use the shared provider runtime. The pipeline's `fit`, `resume`, and `challenge` operations execute through this seam, while the existing truth, evidence, ATS, application-mode, browser, Notion, and approval gates remain unchanged.
