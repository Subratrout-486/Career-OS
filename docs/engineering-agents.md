# Career OS engineering-agent pool

Career OS can optionally use open-source engineering agents for repository repair and debugging. They are **not** part of the normal job-processing provider pool.

## Supported agents

| Agent | Career OS role | Install | Task mode |
|---|---|---|---|
| OpenHands | autonomous coding/debugging | `uv tool install openhands --python 3.12` | `openhands --headless -t "..."` |
| Goose | general engineering/workflows | official Goose installer | `goose run --text "..."` |
| mini-SWE-agent | lightweight SWE repair | `pipx install mini-swe-agent` | `mini -t "..."` |
| Aider | git-aware coding/review | `python -m pip install -U aider-chat` | `aider --message "..."` |

These commands follow the projects' documented headless/CLI modes. OpenHands documents headless execution for CI/scripts; Goose documents `run --text`; mini-SWE-agent documents `mini -t`; Aider documents message/code and architect modes. See the upstream project documentation before enabling automatic approval.

## Career OS interface

`career_os.engineering_agent_pool` discovers installed agents at runtime. Missing agents are reported as unavailable and do not prevent Career OS from starting.

```python
from career_os.engineering_agent_pool import describe_agents, run_engineering_task

print(describe_agents())
result = run_engineering_task(
    "Inspect the failing tests, make the smallest fix, and run the relevant test suite.",
    ".",
    agent="auto",
)
```

The default is conservative: `approve=False`. Do not enable automatic approval for a production workspace until the task has been validated.

## Selection order

`agent="auto"` chooses the first installed agent in this order:

1. OpenHands
2. Goose
3. mini-SWE-agent
4. Aider

This order intentionally prefers the most autonomous engineering agent first, while preserving fallbacks.

## Free/local operation

The agents are open-source/free to install, but the model they use may not be free. For a $0 model path, configure a local model provider such as Ollama where the selected agent supports it. Aider and mini-SWE-agent explicitly support OpenAI-compatible/local endpoints; Goose supports Ollama; OpenHands supports local LLM configurations.

Do not store model/API keys in source control. Use the deployment's secret manager or environment variables.
