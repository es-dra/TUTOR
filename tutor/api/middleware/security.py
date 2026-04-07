"""Security middleware for TUTOR API.

Provides:
- CORS configuration
- Security headers (via custom middleware)
"""

import os
from typing import Any, List, Optional


def configure_cors(
    app: Any,
    allowed_origins: Optional[List[str]] = None,
    allow_credentials: bool = True,
    allow_methods: Optional[List[str]] = None,
    allow_headers: Optional[List[str]] = None,
) -> None:
    """Configure CORS middleware for the FastAPI app.

    Args:
        app: FastAPI application instance
        allowed_origins: List of allowed origins. Defaults to env TUTOR_ALLOWED_ORIGINS
        allow_credentials: Whether to allow credentials
        allow_methods: Allowed HTTP methods. Defaults to standard methods
        allow_headers: Allowed HTTP headers. Defaults to all
    """
    from fastapi.middleware.cors import CORSMiddleware

    if allowed_origins is None:
        allowed_origins_str = os.environ.get(
            "TUTOR_ALLOWED_ORIGINS",
            "http://localhost:3000,http://localhost:5173"
        )
        allowed_origins = [o.strip() for o in allowed_origins_str.split(",") if o.strip()]

    if allow_methods is None:
        allow_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]

    if allow_headers is None:
        allow_headers = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=allow_credentials,
        allow_methods=allow_methods,
        allow_headers=allow_headers,
    )


def configure_security(app: Any) -> None:
    """Configure security middleware for the FastAPI app.

    This includes:
    - CORS configuration
    - Security headers (via custom middleware)

    Note: For full Helmet-style security headers, add the helmet package
    and integrate it here.
    """
    configure_cors(app)

    # Add custom security headers middleware
    @app.middleware("http")
    async def security_headers_middleware(request, call_next):
        response = await call_next(request)

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response
