"""Tests for ApiResponse and PaginatedResponse models."""
import pytest


@pytest.mark.unit
def test_api_response_has_all_required_fields():
    """Verify ApiResponse has success, data, error, meta fields."""
    from tutor.api.models import ApiResponse

    # Test success response
    response = ApiResponse(success=True, data={"key": "value"})
    assert response.success is True
    assert response.data == {"key": "value"}
    assert response.error is None
    assert response.meta is None

    # Test error response
    error_response = ApiResponse(
        success=False,
        error={"code": "NOT_FOUND", "message": "Resource not found"}
    )
    assert error_response.success is False
    assert error_response.error == {"code": "NOT_FOUND", "message": "Resource not found"}


@pytest.mark.unit
def test_paginated_response_has_required_fields():
    """Verify PaginatedResponse has required pagination fields."""
    from tutor.api.models import PaginatedResponse

    response = PaginatedResponse(
        data=[{"id": 1}, {"id": 2}],
        meta={"total": 10, "limit": 2, "offset": 0, "has_more": True}
    )
    assert response.data == [{"id": 1}, {"id": 2}]
    assert response.meta["total"] == 10
    assert response.meta["has_more"] is True
