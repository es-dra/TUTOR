import pytest

@pytest.mark.unit
def test_api_key_comparison_is_timing_safe() -> None:
    """Verify API key comparison uses hmac.compare_digest."""
    import inspect
    from tutor.api.main import api_key_auth_middleware

    source = inspect.getsource(api_key_auth_middleware)

    # Should NOT use != for comparison
    assert "api_key != expected_key" not in source, "Using != for API key comparison"

    # Should use hmac.compare_digest
    assert "hmac.compare_digest" in source or "compare_digest" in source, \
        "Not using timing-safe comparison"
