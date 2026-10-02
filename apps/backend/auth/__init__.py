"""Identity and authorization (Phase 1).

Authentication is pluggable: ``AUTH_PROVIDER=dev`` trusts local headers for
development and tests, ``AUTH_PROVIDER=clerk`` verifies a real OIDC/Clerk JWT
against its JWKS endpoint. Everything downstream reads the same ``Principal``.
"""

from auth.api_keys import generate_key, hash_key, resolve_api_key
from auth.deps import (
    RequestContext,
    get_api_key_project,
    get_current_principal,
    get_current_project,
    get_current_user,
    get_current_workspace,
    get_request_context,
    require_role,
)
from auth.provider import AuthError, Principal, get_auth_provider, reset_auth_provider

__all__ = [
    "AuthError",
    "Principal",
    "get_auth_provider",
    "reset_auth_provider",
    "generate_key",
    "hash_key",
    "resolve_api_key",
    "get_current_principal",
    "get_current_user",
    "get_current_workspace",
    "get_current_project",
    "get_api_key_project",
    "require_role",
    "RequestContext",
    "get_request_context",
]
