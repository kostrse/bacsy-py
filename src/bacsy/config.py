"""Endpoint, transport, retry and streaming configuration for the BCS Trade API."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal

from bacsy._version import __version__
from bacsy.routes import Service

if TYPE_CHECKING:
    from collections.abc import Mapping

DEFAULT_REST_BASE_URL = "https://be.broker.ru"
"""Base URL serving the REST API and the authorization endpoint."""

DEFAULT_WS_BASE_URL = "wss://ws.broker.ru"
"""Base URL serving the WebSocket streams."""

TOKEN_ENDPOINT_PATH = "/trade-api-keycloak/realms/tradeapi/protocol/openid-connect/token"
"""Path of the OpenID Connect token endpoint that exchanges a refresh token."""

DEFAULT_TIMEOUT_SECONDS = 30.0
"""Default total timeout applied to a single REST request."""

DEFAULT_USER_AGENT = f"bacsy/{__version__}"
"""Default `User-Agent` header of the connection pool and WebSocket connector the client
creates."""

DEFAULT_SERVICE_RPS: Mapping[Service, float] = MappingProxyType(
    {
        **dict.fromkeys(Service, 10.0),
        Service.NONTRADE_OPERATIONS: 3.0,
    }
)
"""Documented requests-per-second limit of each service, per client account."""


@dataclass(frozen=True, slots=True, kw_only=True)
class RateLimitConfig:
    """Client-side pacing of requests against the documented per-service limits."""

    enabled: bool = True
    safety_factor: float = 0.9
    """Fraction of the documented limit the client allows itself to use."""
    overrides: Mapping[Service, float] = field(default_factory=lambda: {})
    """Per-service requests-per-second replacing the documented value."""

    def rate_for(self, service: Service) -> float:
        """Return the effective requests-per-second budget for `service`."""
        documented = self.overrides.get(service, DEFAULT_SERVICE_RPS[service])
        return documented * self.safety_factor


@dataclass(frozen=True, slots=True, kw_only=True)
class RetryPolicy:
    """Retry and backoff behaviour of the REST transport.

    Transport failures and server errors are retried only for idempotent operations. A
    429 is retried for every operation unless `retry_writes_on_429` is `False`, which
    excludes non-idempotent operations.
    """

    max_attempts: int = 3
    base_delay: float = 0.5
    max_delay: float = 8.0
    multiplier: float = 2.0
    jitter: bool = True
    retry_statuses: frozenset[int] = frozenset({429, 500, 502, 503, 504})
    retry_transport_errors: bool = True
    retry_writes_on_429: bool = True
    rate_limit_floor: float = 1.0
    """Minimum delay after a 429; the documented limit window is one second."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ReconnectPolicy:
    """Reconnection behaviour of WebSocket streams."""

    enabled: bool = True
    max_attempts: int | None = None
    """Consecutive failed reconnects before giving up; `None` retries forever."""
    base_delay: float = 1.0
    max_delay: float = 30.0
    multiplier: float = 2.0
    jitter: bool = True


OverflowPolicy = Literal["drop_oldest", "block"]


@dataclass(frozen=True, slots=True, kw_only=True)
class StreamOptions:
    """Buffering, heartbeat and pacing options of WebSocket streams."""

    queue_size: int = 1000
    overflow: OverflowPolicy = "drop_oldest"
    """What to do when the consumer falls behind by `queue_size` events."""
    ping_interval: float | None = 20.0
    ping_timeout: float | None = 20.0
    send_rate: float = 8.0
    """Client messages per second; the API allows ten."""
    enforce_connection_caps: bool = True
    """Refuse to open more concurrent connections per service than the API allows."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ClientConfig:
    """Immutable configuration shared by the REST and WebSocket clients."""

    rest_base_url: str = DEFAULT_REST_BASE_URL
    ws_base_url: str = DEFAULT_WS_BASE_URL
    token_endpoint_path: str = TOKEN_ENDPOINT_PATH
    """Path of the token endpoint, relative to `rest_base_url`."""
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    user_agent: str = DEFAULT_USER_AGENT
    """`User-Agent` header of the HTTP connection pool and WebSocket connector created from
    this configuration. An injected pool or connector keeps its own headers.
    """
    access_token_skew_seconds: float = 60.0
    """Refresh the access token this many seconds before it expires."""
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    reconnect: ReconnectPolicy = field(default_factory=ReconnectPolicy)
    stream: StreamOptions = field(default_factory=StreamOptions)
