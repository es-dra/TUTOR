def test_env_example_has_no_real_keys():
    """Verify .env.example contains only placeholders, not real keys."""
    from pathlib import Path

    env_example = Path(__file__).parent.parent.parent / ".env.example"
    content = env_example.read_text(encoding="utf-8")

    # Check for common API key patterns - should NOT contain real keys
    assert "sk-cp-d1YpMP1TD" not in content, "Real MiniMax key found in .env.example"
    assert "sk-" not in content or "sk-your" in content.lower(), "Real OpenAI key found"
    assert "sk-ant-" not in content or "sk-ant-api" in content.lower(), "Real Anthropic key found"
