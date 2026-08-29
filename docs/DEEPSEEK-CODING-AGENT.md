# DeepSeek coding agent

Career OS now has a provider adapter for DeepSeek that can drive the isolated
`CodingRepairAgent` without giving the model shell access or production access.

## Runtime boundary

```text
failure/test result
      |
      v
CodingRepairAgent
      |
      +--> DeepSeekCodingProposer -- returns unified diff only
      |
      +--> git apply --check
      |
      +--> apply patch
      |
      +--> allow-listed test command
      |
      +--> REPAIRED or rollback
```

The repair agent is intentionally isolated from the live orchestration path.
It does not commit, push, deploy, change secrets, or execute model-provided
commands. Production changes remain behind the existing approval boundary.

## Configuration

Set the existing GitHub/Deployment secret:

`DEEPSEEK_API_KEY`

Optional:

- `DEEPSEEK_CODING_MODEL` (default: `deepseek-v4-pro`)
- `DEEPSEEK_BASE_URL` (default: `https://api.deepseek.com`)

The adapter uses DeepSeek's OpenAI-compatible `/chat/completions` API and
expects a unified diff in the response. Current DeepSeek V4 models support
reasoning and tool calls, but this adapter deliberately does not expose tools:
the Career OS repair runtime owns all filesystem and test execution.

## Example

```python
from career_os.coding_agent import CodingRepairAgent
from career_os.deepseek_coding import DeepSeekCodingProposer

proposer = DeepSeekCodingProposer()
agent = CodingRepairAgent(
    "/path/to/isolated/worktree",
    propose_patch=proposer.propose_patch,
    test_command=("python", "-m", "pytest", "-q"),
)
result = agent.repair("pytest failed in the job ingestion module")
```

A successful result is only `REPAIRED` after the patch applies and the configured
verification command exits successfully. Failed attempts are rolled back.
