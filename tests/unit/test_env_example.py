"""Verify .env.example contains only placeholders, not real API keys."""

import pytest


@pytest.mark.unit
def test_env_example_has_no_real_keys() -> None:
    """Verify .env.example contains only placeholders, not real keys."""
    from pathlib import Path

    env_example = Path(__file__).parent.parent.parent / ".env.example"
    content = env_example.read_text(encoding="utf-8")

    # Check for common API key patterns - should NOT contain real keys
    assert "sk-cp-d1YpMP1TD" not in content, "Real MiniMax key found in .env.example"
    assert not any(
        line.strip().startswith("sk-") and "your" not in line.lower()
        for line in content.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ), "Real API key found in .env.example"
    assert "sk-ant-" not in content or "sk-ant-api" in content.lower(), "Real Anthropic key found"
