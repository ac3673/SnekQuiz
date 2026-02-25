"""HTTP authentication helpers.

Two user roles:
- **admin** - can upload quizzes and view aggregated results
- **user**  - can browse and take quizzes

Authentication is attempted in order:
1. Local config-defined ``admins`` / ``users`` maps
2. LDAP simple-bind (when ``ldap.server_url`` is configured)
"""

from __future__ import annotations

import logging
import secrets
from contextlib import suppress
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

if TYPE_CHECKING:
    from snekquiz.models import LdapSettings

logger = logging.getLogger("snekquiz.auth")

security = HTTPBasic()

# Populated at startup from Settings.auth
_admins: dict[str, str] = {}
_users: dict[str, str] = {}
_ldap: LdapSettings | None = None


def load_users(
    admins: dict[str, str],
    users: dict[str, str],
    ldap: LdapSettings | None = None,
) -> None:
    """Load the user/password mappings and optional LDAP config."""
    _admins.update(admins)
    _users.update(users)
    global _ldap
    _ldap = ldap
    logger.info(
        "Loaded %d admin(s), %d user(s), LDAP %s",
        len(_admins),
        len(_users),
        "enabled" if ldap and ldap.server_url else "disabled",
    )


# ---------------------------------------------------------------------------
# Local credential check
# ---------------------------------------------------------------------------


def _check_local(credentials: HTTPBasicCredentials) -> tuple[str, bool] | None:
    """Check local admins/users maps. Returns (username, is_admin) or None."""
    for store, is_admin in ((_admins, True), (_users, False)):
        expected_password = store.get(credentials.username)
        if expected_password is not None and secrets.compare_digest(
            credentials.password.encode("utf-8"),
            expected_password.encode("utf-8"),
        ):
            return credentials.username, is_admin
    return None


# ---------------------------------------------------------------------------
# LDAP authentication
# ---------------------------------------------------------------------------


def _check_ldap(credentials: HTTPBasicCredentials) -> tuple[str, bool] | None:
    """Attempt LDAP simple-bind. Returns (username, is_admin) or None.

    The ``domain`` setting is prepended as ``DOMAIN\\username`` for the bind.
    After a successful bind the connection is searched for group membership
    when ``admin_groups`` is configured.
    """
    if _ldap is None or not _ldap.server_url:
        return None

    try:
        import ldap3
        from ldap3.core.exceptions import LDAPException
    except ImportError:
        logger.warning("ldap3 package not installed - LDAP auth unavailable")
        return None

    bind_user = credentials.username
    if _ldap.domain:
        bind_user = f"{_ldap.domain}\\{credentials.username}"

    server = ldap3.Server(_ldap.server_url, use_ssl=_ldap.use_ssl, get_info=ldap3.NONE)
    conn = ldap3.Connection(server, user=bind_user, password=credentials.password)

    try:
        if not conn.bind():
            logger.debug("LDAP bind failed for %r: %s", bind_user, conn.result)
            return None
    except LDAPException:
        logger.exception("LDAP connection error for %r", bind_user)
        return None

    logger.info("LDAP bind succeeded for %r", bind_user)

    # Determine admin status via group membership
    is_admin = False
    if _ldap.admin_groups:
        is_admin = _ldap_check_admin_groups(conn, credentials.username)

    with suppress(LDAPException):
        conn.unbind()

    return credentials.username, is_admin


def _ldap_check_admin_groups(conn: object, username: str) -> bool:
    """Search the bound connection for membership in any configured admin group."""
    import ldap3

    if _ldap is None:
        return False

    try:
        # Search for the user's group memberships via a broad
        # subtree search.  The filter matches sAMAccountName (AD)
        # or uid and checks memberOf against the configured admin
        # group CNs.
        esc = ldap3.utils.conv.escape_filter_chars  # type: ignore[attr-defined]
        group_filters = "".join(f"(memberOf=*{esc(g)}*)" for g in _ldap.admin_groups)
        escaped = esc(username)
        search_filter = f"(&(|(sAMAccountName={escaped})(uid={escaped}))(|{group_filters}))"

        conn.search(  # type: ignore[union-attr]
            search_base="",
            search_filter=search_filter,
            search_scope=ldap3.SUBTREE,
            attributes=["memberOf"],
        )
        if conn.entries:  # type: ignore[union-attr]
            logger.debug(
                "User %r matched admin group filter",
                username,
            )
            return True
    except Exception:
        logger.exception(
            "LDAP admin-group search failed for %r",
            username,
        )

    return False


# ---------------------------------------------------------------------------
# Unified verify
# ---------------------------------------------------------------------------


def _verify(credentials: HTTPBasicCredentials) -> tuple[str, bool]:
    """Validate credentials; return (username, is_admin) or raise 401.

    Checks local stores first, then falls back to LDAP.
    """
    result = _check_local(credentials)
    if result is not None:
        return result

    result = _check_ldap(credentials)
    if result is not None:
        return result

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Basic"},
    )


def get_current_user(
    credentials: Annotated[HTTPBasicCredentials, Depends(security)],
) -> tuple[str, bool]:
    """FastAPI dependency - returns (username, is_admin)."""
    return _verify(credentials)


def get_admin_user(
    user: Annotated[tuple[str, bool], Depends(get_current_user)],
) -> str:
    """FastAPI dependency - returns admin username or raises 403."""
    username, is_admin = user
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return username


async def get_optional_user(request: Request) -> tuple[str, bool] | None:
    """Try to extract Basic credentials without forcing a 401."""
    auth = request.headers.get("Authorization")
    if auth is None:
        return None
    try:
        import base64

        scheme, _, param = auth.partition(" ")
        if scheme.lower() != "basic":
            return None
        decoded = base64.b64decode(param).decode("utf-8")
        username, _, password = decoded.partition(":")
        creds = HTTPBasicCredentials(username=username, password=password)
        return _verify(creds)
    except Exception:
        return None
