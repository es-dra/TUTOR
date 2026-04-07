"""Tests for health routes module."""
import pytest


@pytest.mark.unit
def test_health_routes_exist_in_separate_module():
    """Verify health routes are in tutor.api.routes.health."""
    from tutor.api.routes import health
    assert hasattr(health, "router")
    assert hasattr(health, "health_check")
    assert hasattr(health, "health_live")
    assert hasattr(health, "health_ready")
