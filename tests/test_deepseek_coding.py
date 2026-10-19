from career_os.deepseek_coding import DeepSeekCodingError, DeepSeekCodingProposer, _extract_patch


def test_extracts_fenced_git_diff():
    patch = _extract_patch("```diff\ndiff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n```\n")
    assert patch.startswith("diff --git a/x.py b/x.py")


def test_extracts_plain_unified_diff():
    patch = _extract_patch("--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n")
    assert patch.startswith("--- a/x.py")


def test_rejects_non_patch_output():
    try:
        _extract_patch("I changed the code for you.")
    except DeepSeekCodingError as exc:
        assert "unified diff" in str(exc)
    else:
        raise AssertionError("non-patch model output was accepted")


def test_requires_api_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    try:
        DeepSeekCodingProposer()
    except DeepSeekCodingError as exc:
        assert "DEEPSEEK_API_KEY" in str(exc)
    else:
        raise AssertionError("missing DeepSeek credential was accepted")
