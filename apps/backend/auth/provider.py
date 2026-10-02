"""Pluggable authentication providers.

Both providers return the same :class:`Principal`, so routes and dependencies
never need to know whether the caller came from local headers or a real Clerk
OIDC token.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Protocol

from config.settings import get_settings
from fastapi import Request

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Credentials are missing or invalid."""


@dataclass
class Principal:
    """Who the caller is, independent of the identity provider."""

    subject: str
    email: str
    name: Optional[str] = None
    # Identity-provider organization identifier (Clerk `org_id`).
    workspace_external_id: Optional[str] = None


class AuthProvider(Protocol):
    """Verifies an incoming request and returns a principal."""

    def authenticate(self, request: Request) -> Principal:  # pragma: no cover - protocol
        ...


class DevAuthProvider:
    """Header-derived identity for local development and tests.

    Never enable this in a deployment reachable by untrusted clients: it trusts
    the caller to say who they are.
    """

    def authenticate(self, request: Request) -> Principal:
        settings = get_settings()
        # Headers are the normal path. Query parameters are accepted too because
        # the browser EventSource API cannot set headers, and the dashboard
        # streams (SSE) still need an identity in development.
        params = request.query_params
        email = (
            request.headers.get("x-dev-user-email")
            or params.get("dev_user_email")
            or settings.dev_user_email
        )
        name = (
            request.headers.get("x-dev-user-name")
            or params.get("dev_user_name")
            or settings.dev_user_name
        )
        workspace = (
            request.headers.get("x-dev-workspace")
            or params.get("dev_workspace")
            or settings.dev_workspace_slug
        )
        return Principal(
            subject=f"dev:{email}",
            email=email,
            name=name,
            workspace_external_id=workspace,
        )


class ClerkAuthProvider:
    """Verifies a Clerk/OIDC bearer token against the issuer's JWKS."""

    def __init__(self, jwks_url: str, issuer: str, audience: Optional[str] = None) -> None:
        import jwt
        from jwt import PyJWKClient

        self._jwt = jwt
        self._jwks = PyJWKClient(jwks_url, cache_keys=True)
        self._issuer = issuer
        self._audience = audience

    def authenticate(self, request: Request) -> Principal:
        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer "):
            raise AuthError("Missing bearer token")
        token = header.split(" ", 1)[1].strip()

        try:
            signing_key = self._jwks.get_signing_key_from_jwt(token)
            claims = self._jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
                options={"verify_aud": bool(self._audience)},
            )
        except Exception as exc:  # invalid signature, expired, wrong issuer, ...
            raise AuthError(f"Invalid credentials: {exc}") from exc

        subject = str(claims.get("sub") or "")
        email = claims.get("email") or (f"{subject}@clerk.local" if subject else "")
        if not email:
            raise AuthError("Token is missing a subject")

        return Principal(
            subject=subject,
            email=str(email),
            name=claims.get("name"),
            workspace_external_id=claims.get("org_id") or claims.get("org_slug"),
        )


_provider: Optional[AuthProvider] = None


def reset_auth_provider() -> None:
    """Forget the cached provider (tests, or after changing settings)."""
    global _provider
    _provider = None


def get_auth_provider() -> AuthProvider:
    """Return the configured provider, creating it on first use."""
    global _provider
    if _provider is None:
        settings = get_settings()
        name = (settings.auth_provider or "dev").lower()

        if name == "dev":
            logger.warning(
                "AUTH_PROVIDER=dev trusts caller-supplied identity headers; "
                "do not use this for anything reachable by untrusted clients."
            )
            _provider = DevAuthProvider()
        elif name == "clerk":
            if not settings.clerk_jwks_url or not settings.clerk_issuer:
                raise AuthError("AUTH_PROVIDER=clerk requires CLERK_JWKS_URL and CLERK_ISSUER")
            _provider = ClerkAuthProvider(
                settings.clerk_jwks_url, settings.clerk_issuer, settings.clerk_audience
            )
        else:
            raise AuthError(f"Unknown AUTH_PROVIDER: {settings.auth_provider!r}")

    return _provider
