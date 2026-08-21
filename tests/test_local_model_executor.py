from unittest.mock import patch

from career_os.local_model_executor import OllamaModelExecutor


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b'{"message":{"content":"{\\"ok\\":true}"}}'


async def test_ollama_executor_posts_to_local_server():
    executor = OllamaModelExecutor(model="test-model")
    with patch("career_os.local_model_executor.urlopen", return_value=_Response()) as open_url:
        result = await executor.generate(system="system", user="user", json_mode=True, max_tokens=10)
    assert result == '{"ok":true}'
    request = open_url.call_args.args[0]
    assert request.full_url == "http://127.0.0.1:11434/api/chat"
