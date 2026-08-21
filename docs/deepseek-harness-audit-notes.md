# DeepSeek Harness audit notes

Source: https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/architecture.md

The official architecture is Cordis-based and treats every capability as a plugin. Plugins contribute services, typed events, and reversible effects to a shared context. The model adapter, tool registry, session log, and agent loop are all replaceable from configuration; there is no privileged core to patch.

Profiles compose ordered bundles and patch overlays. The base layer includes model adapters, tools, persistence, sandbox and approval policy, settings, credentials, telemetry, and related infrastructure.

Core seams include a durable append-only session event log, prompt/tool-schema assembly, a scoped tool registry with guarded execution, an agent registry and events, an agent loop, and an LLM adapter seam. A step is one model request plus its tool calls. A turn contains zero or more steps and is durable across turn/start, step/start, model request, assistant message, tool call/result, step/end, and turn/end events.

The tool lifecycle is explicitly pre-execute -> execute -> post-execute, with tool schemas included in prompt assembly. Capability seams have three roles: a service definition, a provider, and a consumer. Provider replacement should occur behind the same seam rather than through provider-specific forks.

The relevant Career OS adaptation should therefore consolidate around one provider-agnostic runtime with explicit registries and durable events, while preserving the existing ControlPlaneStore, AgentRuntime provider adapters, truth/evidence gates, application-mode policy, approval gates, browser lifecycle, and Conductor review-only boundary.

Additional official source: https://deepseek.com/harness/en/

The official product description states: Agent = Model + Harness. The harness lets an agent understand its environment, use tools, and keep working in real-world settings. Cordis manages plugin mounting, unmounting, and dependencies. Plugins provide models, tools, skills, sessions, sandboxes, storage, loops, scheduling, and UI, while configuration selects, swaps, or extends capabilities without changing the Harness source.
