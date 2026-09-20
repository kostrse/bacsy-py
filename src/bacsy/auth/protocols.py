"""Authentication protocols.

The protocols are structural: any object with the matching methods satisfies them.
Bundled implementations live in `bacsy.auth.provider` and `bacsy.auth.cache`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from bacsy.auth.tokens import AccessToken, TokenScope


class AccessTokenProvider(Protocol):
    """Supplies bearer tokens for API requests and WebSocket handshakes.

    How a token is obtained is up to the implementation; callers ask for a scope and
    report tokens the API rejected.
    """

    async def get(self, scope: TokenScope) -> str:
        """Return a token expected to be valid for `scope`, refreshing if necessary."""
        ...

    async def invalidate(self, token: str) -> None:
        """Record that the API rejected `token` so that a later `get` can return a replacement.

        An implementation that cannot replace the token may keep returning it.
        """
        ...


class AccessTokenCache(Protocol):
    """Storage for minted access tokens, keyed by the refresh token's session id."""

    async def get(self, sid: str) -> AccessToken | None:
        """Return the token stored for `sid`, or `None`."""
        ...

    async def set(self, sid: str, token: AccessToken) -> None:
        """Store `token` for `sid`, replacing any existing entry."""
        ...

    async def delete(self, sid: str) -> None:
        """Remove the entry for `sid`, if any."""
        ...
