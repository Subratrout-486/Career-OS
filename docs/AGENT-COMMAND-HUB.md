# Career OS Agent Command Hub

Career OS now has a registry-driven agent command layer.

## How it works

`config/agent_registry.json` is the declarative control file. It contains:

- specialist agents
- capabilities
- commands each agent accepts
- runtime boundary (`builtin` or `conductor`)
- approval boundary
- command → agent routing

`src/career_os/agent_hub.py` loads this registry and resolves commands without hard-coding agent selection into the dashboard or individual workflows.

## Dispatch contract

Career OS can call:

`POST /api/agent-hub/dispatch`

with a command, objective and optional input/evidence. The hub resolves the command to a registered agent, creates a durable Career OS task when necessary, and records an `AgentMessage` addressed to that agent.

A successful dispatch means **queued**, not **executed**. External AI execution remains at the configured runtime boundary. The runtime must report the result through:

`POST /api/tasks/{task_id}/result`

This distinction is intentional: Career OS must never claim an AI agent ran when it only created a handoff.

## Example command flow

`tailor_resume`

→ `resume` agent

→ Conductor runtime

→ resume task executes using confirmed Career Evidence

→ result returns to Career OS

→ Truth Guard / ATS / reviewer can be dispatched as follow-up commands

## Approval boundaries

Commands that can have consequential effects declare an approval boundary in the registry. Browser submission is `before_submit`; production engineering changes are `before_production_change`.

The registry contains no credentials. Provider credentials and runtime connectivity remain external configuration.

## Extending the system

To add a specialist:

1. Add its definition to `config/agent_registry.json`.
2. Give it explicit capabilities and commands.
3. Add command routing.
4. Connect the runtime adapter that can actually execute those commands.
5. Make the runtime report the structured result back to Career OS.

This makes agents replaceable without changing the Career OS UI or core control-plane contracts.
