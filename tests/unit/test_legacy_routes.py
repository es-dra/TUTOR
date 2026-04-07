"""Tests for legacy routes module."""
import pytest


@pytest.mark.unit
def test_legacy_routes_marked_deprecated():
    """Verify legacy routes are in separate module and marked deprecated."""
    from tutor.api.routes import legacy
    assert hasattr(legacy, "router")

    # Check that routes are marked deprecated
    for route in legacy.router.routes:
        if hasattr(route, "deprecated"):
            assert route.deprecated is True, f"Route {route.path} not marked deprecated"
