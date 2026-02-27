"""HTTP authentication helpers.

Two user roles:
- **admin** - can upload quizzes and view aggregated results
- **user**  - can browse and take quizzes

Authentication is attempted in order:
1. Local config-defined ``admins`` / ``users`` maps
2. LDAP simple-bind (when ``ldap.server_url`` is configured)
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from typing import TYPE_CHECKING, Any

import ldap3
from fastapi import HTTPException, status
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars
from pydantic import BaseModel

if TYPE_CHECKING:
    from fastapi.security import HTTPBasicCredentials
    from pydantic import SecretStr

    from .models import AuthSettings

log = logging.getLogger(__name__)


def hash_password(password: str, salt: bytes | None = None) -> bytes:
    """
    Hash a password with a salt using PBKDF2-HMAC-SHA256.

    Args:
        password: The password to hash
        salt: Optional salt bytes. If None, a random salt is generated.

    Returns:
        The salt + hash concatenated as bytes
    """
    if salt is None:
        salt = secrets.token_bytes(32)  # 32 bytes = 256 bits

    # Hash the password with PBKDF2-HMAC
    key: bytes = hashlib.pbkdf2_hmac(
        hash_name="sha256",
        password=password.encode("utf-8"),
        salt=salt,
        iterations=600_000,  # OWASP recommendation for 2023+
        dklen=32,  # Desired length of derived key
    )

    # Return salt + key concatenated
    return salt + key


def verify_password(stored_password: bytes, provided_password: str) -> bool:
    """
    Verify a password against a stored hash.

    Args:
        stored_password: The stored salt + hash bytes
        provided_password: The password to verify

    Returns:
        True if password matches, False otherwise
    """
    # Extract the salt (first 32 bytes)
    salt: bytes = stored_password[:32]
    stored_key: bytes = stored_password[32:]

    # Hash the provided password with the same salt
    provided_key: bytes = hashlib.pbkdf2_hmac(
        hash_name="sha256",
        password=provided_password.encode("utf-8"),
        salt=salt,
        iterations=600_000,
        dklen=32,
    )

    # Use constant-time comparison to prevent timing attacks
    return secrets.compare_digest(stored_key, provided_key)


class User(BaseModel):
    username: str
    is_admin: bool
    full_name: str


class CachedUser(User):
    password_hash: bytes


class AuthManager:
    def __init__(self, s: AuthSettings):
        self._settings = s
        self._admins: dict[str, SecretStr] = s.admins
        self._users: dict[str, SecretStr] = s.users
        self._auth_cache: dict[str, CachedUser] = {}
        self._ldap_enabled = s.ldap and s.ldap.server_url
        log.info(
            "Loaded %d admin(s), %d user(s), LDAP is %s",
            len(self._admins),
            len(self._users),
            f"enabled (admin groups: {s.ldap.admin_groups})" if self._ldap_enabled else "disabled",
        )

    # ---------------------------------------------------------------------------
    # Local credential check
    # ---------------------------------------------------------------------------

    def _check_local(self, credentials: HTTPBasicCredentials) -> User | None:
        """Check local admins/users maps. Returns (username, is_admin) or None."""
        for store, is_admin in ((self._admins, True), (self._users, False)):
            expected_password = store.get(credentials.username)
            if expected_password is not None and secrets.compare_digest(
                credentials.password.encode("utf-8"),
                expected_password.get_secret_value().encode("utf-8"),
            ):
                return User(
                    username=credentials.username,
                    is_admin=is_admin,
                    full_name=credentials.username,
                )
        return None

    # ---------------------------------------------------------------------------
    # LDAP authentication
    # ---------------------------------------------------------------------------

    def _check_ldap(self, credentials: HTTPBasicCredentials) -> User | None:
        """Attempt LDAP simple-bind. Returns (username, is_admin) or None.

        The ``domain`` setting is prepended as ``DOMAIN\\username`` for the bind.
        After a successful bind the connection is searched for group membership
        when ``admin_groups`` is configured.
        """
        if not self._ldap_enabled:
            return None
        name = credentials.username
        is_admin = False
        bind_user = credentials.username
        if self._settings.ldap.domain:
            bind_user = f"{self._settings.ldap.domain}\\{credentials.username}"

        server = ldap3.Server(
            self._settings.ldap.server_url, use_ssl=self._settings.ldap.use_ssl, get_info=ldap3.NONE
        )
        with ldap3.Connection(server, user=bind_user, password=credentials.password) as conn:
            try:
                if not conn.bind():
                    log.debug(f"LDAP bind failed for {bind_user=} {conn.result}")
                    return None
            except LDAPException:
                log.exception(f"LDAP connection error for {bind_user}")
                return None
            log.info("LDAP bind succeeded for %r", bind_user)
            try:
                # Search for the user's group memberships and name
                group_attrib = self._settings.ldap.group_attrib
                name_attrib = self._settings.ldap.name_attrib
                conn.search(
                    search_base=self._settings.ldap.search_base,
                    search_filter=self._settings.ldap.search_filter.format(
                        username=escape_filter_chars(credentials.username)
                    ),
                    search_scope=ldap3.SUBTREE,
                    attributes=[group_attrib, name_attrib],
                )
                entry: ldap3.Entry = conn.entries[0]
                attribs: dict[str, Any] = entry.entry_attributes_as_dict

                def _get_group_cn(dn: str):
                    for part in dn.split(","):
                        if part.startswith("CN="):
                            return part.split("=")[1]
                    return dn

                groups: list[str] = [_get_group_cn(g) for g in attribs.get(group_attrib, [])]
                name: str = attribs.get(name_attrib, [credentials.username])[0]
                is_admin = self._check_if_user_is_admin(credentials.username, groups)
            except LDAPException:
                log.exception(f"LDAP search error for {bind_user}")
        return User(username=credentials.username, is_admin=is_admin, full_name=name)

    def _check_if_user_is_admin(self, username: str, groups: list[str]) -> bool:
        """Search the bound connection for membership in any configured admin group."""
        if username in self._settings.ldap.admin_users:
            log.debug(f"User is in admin list {username}")
            return True
        if self._settings.ldap.admin_groups:
            valid_groups: list[str] = [g for g in groups if g in self._settings.ldap.admin_groups]
            if any(valid_groups):
                log.debug(f"User matched admin group filter {username=} {valid_groups=}")
                return True
        return False

    # ---------------------------------------------------------------------------
    # User authentication
    # ---------------------------------------------------------------------------

    def authenticate_user(self, credentials: HTTPBasicCredentials) -> User:
        """Validate credentials; return (username, is_admin) or raise 401.

        Checks local stores first, then falls back to LDAP.
        """

        if cached := self._auth_cache.get(credentials.username):  # noqa: SIM102
            if verify_password(cached.password_hash, credentials.password):
                return User(**cached.model_dump(exclude={"password_hash"}))

        if user := self._check_local(credentials):
            return user

        if user := self._check_ldap(credentials):
            self._auth_cache[credentials.username] = CachedUser(
                username=user.username,
                password_hash=hash_password(credentials.password),
                is_admin=user.is_admin,
                full_name=user.full_name,
            )
            return user

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
