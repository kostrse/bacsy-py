"""Behaviour of `TradeApiClient` as a composition root."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest

import bacsy
from bacsy import (
    DEFAULT_USER_AGENT,
    AccountNotFoundError,
    ApiHttpClient,
    ClientConfig,
    ConfigurationError,
    InvalidTokenError,
    RateLimitConfig,
    RetryPolicy,
    TradeApiClient,
    new_http_pool,
)
from bacsy.accounts import AccountManager, AccountStore
from bacsy.auth import (
    MemoryAccessTokenCache,
    StaticAccessTokenProvider,
    TokenScope,
)
from bacsy.exceptions import AuthenticationError, RateLimitError, TransportError
from tests.auth.fakes import DAY, make_refresh_token

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.conftest import ClientFactory

PORTFOLIO = "/trade-api-bff-portfolio/api/v1/portfolio"
LIMITS = "/trade-api-bff-limit/api/v1/limits"
ORDERS = "/trade-api-bff-operations/api/v1/orders"
FAR = 4_000_000_000
NO_PACING = ClientConfig(rate_limit=RateLimitConfig(enabled=False))


def _refresh_token(scope: TokenScope = TokenScope.READ, *, sid: str) -> str:
    return make_refresh_token(scope=scope, exp=FAR + 30 * DAY, sid=sid)


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True})


def _token_response(request: httpx.Request) -> httpx.Response:
    client_id = dict(pair.split("=") for pair in request.read().decode().split("&"))["client_id"]
    return httpx.Response(
        200,
        json={
            "access_token": f"minted-{client_id.removeprefix('trade-api-')}",
            "expires_in": 86400,
            "refresh_token": "rotated",
            "refresh_expires_in": 7776000,
            "token_type": "bearer",
        },
    )


def _recording_handler(seen: list[httpx.Request]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.startswith("/trade-api-keycloak/"):
            return _token_response(request)
        return httpx.Response(200, json={})

    return handler


async def test_sends_bearer_token_and_accept_header(make_client: ClientFactory) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler)
    payload = await client.http.request("GET", PORTFOLIO)

    assert payload == {"ok": True}
    assert seen[0].headers["Authorization"] == "Bearer test-token"
    assert seen[0].headers["Accept"] == "application/json"
    assert str(seen[0].url) == f"https://be.broker.ru{PORTFOLIO}"


async def test_passes_query_parameters_and_json_body(make_client: ClientFactory) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    client = make_client(handler)
    await client.http.request(
        "POST",
        "/trade-api-market-data-connector/api/v1/quotes",
        params={"limit": 5},
        json={"tickers": ["SBER"]},
    )

    assert seen[0].url.params["limit"] == "5"
    assert seen[0].read() == b'{"tickers":["SBER"]}'
    assert seen[0].headers["Content-Type"] == "application/json"


async def test_custom_headers_override_defaults(make_client: ClientFactory) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    client = make_client(handler)
    await client.http.request("GET", LIMITS, headers={"Accept": "application/json; version=2"})

    assert seen[0].headers["Accept"] == "application/json; version=2"


def _spy_created_pools(monkeypatch: pytest.MonkeyPatch) -> list[httpx.AsyncClient]:
    pools: list[httpx.AsyncClient] = []

    def spy(config: ClientConfig) -> httpx.AsyncClient:
        pools.append(new_http_pool(config))
        return pools[-1]

    monkeypatch.setattr("bacsy.client.new_http_pool", spy)
    return pools


async def test_factory_pool_sends_library_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    pools = _spy_created_pools(monkeypatch)
    async with TradeApiClient.from_access_token("test-only-not-a-token"):
        assert pools[0].headers["User-Agent"] == DEFAULT_USER_AGENT
        assert f"bacsy/{bacsy.__version__}" == DEFAULT_USER_AGENT


async def test_factory_pool_sends_configured_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    pools = _spy_created_pools(monkeypatch)
    config = ClientConfig(user_agent="bacsy-tests/1.0")
    async with TradeApiClient.from_access_token("test-only-not-a-token", config=config):
        assert pools[0].headers["User-Agent"] == "bacsy-tests/1.0"


async def test_injected_pool_keeps_its_own_user_agent() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    config = ClientConfig(user_agent="ignored/9")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url=config.rest_base_url,
        headers={"User-Agent": "custom/1"},
    ) as pool:
        client = TradeApiClient.from_access_token("test-only-not-a-token", config=config, http=pool)
        await client.http.request("GET", LIMITS)
        await client.http.request("GET", LIMITS, headers={"User-Agent": "per-request/2"})

    assert [r.headers["User-Agent"] for r in seen] == ["custom/1", "per-request/2"]


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [(401, AuthenticationError), (429, RateLimitError)],
)
async def test_error_responses_raise(
    make_client: ClientFactory, status_code: int, expected: type[Exception]
) -> None:
    config = ClientConfig(retry=RetryPolicy(max_attempts=1))
    client = make_client(lambda _: httpx.Response(status_code, text="nope"), config=config)

    with pytest.raises(expected) as exc_info:
        await client.http.request("GET", PORTFOLIO)

    response = getattr(exc_info.value, "response", None)
    assert response is not None
    assert response.body == "nope"


async def test_transport_failures_are_wrapped(make_client: ClientFactory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    client = make_client(handler, config=ClientConfig(retry=RetryPolicy(max_attempts=1)))

    with pytest.raises(TransportError, match=f"GET {PORTFOLIO} failed"):
        await client.http.request("GET", PORTFOLIO)


async def test_does_not_close_an_injected_http_client(make_client: ClientFactory) -> None:
    client = make_client(_ok)

    async with client:
        pass

    # The injected client is still usable after the context manager exits.
    assert await client.http.request("GET", LIMITS) == {"ok": True}


async def test_factory_closes_the_pool_it_created() -> None:
    client = TradeApiClient.from_access_token("t")

    async with client:
        assert client.config.rest_base_url == "https://be.broker.ru"

    with pytest.raises(RuntimeError):
        await client.http.request("GET", LIMITS)


async def test_factory_leaves_an_injected_pool_open() -> None:
    seen: list[httpx.Request] = []
    pool = _pool(seen)

    async with TradeApiClient.from_access_token("t", http=pool, config=NO_PACING) as client:
        await client.http.request("GET", LIMITS)
    assert not pool.is_closed
    await pool.aclose()

    assert seen[0].headers["Authorization"] == "Bearer t"


async def test_services_and_streams_share_the_http_client() -> None:
    http = ApiHttpClient(StaticAccessTokenProvider("t"), http=_pool([]))
    client = TradeApiClient(http)

    assert client.http is http
    assert client.config is http.config
    assert client.portfolio is client.portfolio
    await http.aclose()


async def test_unnamed_account_raises_configuration_error() -> None:
    with pytest.raises(ConfigurationError, match="no account name given"):
        TradeApiClient.from_account(http=_pool([]), config=NO_PACING)


async def test_missing_account_raises_configuration_error() -> None:
    client = TradeApiClient.from_account("ghost", http=_pool([]), config=NO_PACING)

    with pytest.raises(AccountNotFoundError, match="no account named 'ghost'"):
        await client.http.request("GET", LIMITS)


async def test_from_account_reads_the_accounts_file(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    manager = AccountManager.from_file(tmp_path / "accounts.json")
    await manager.add_token("acct", _refresh_token(TokenScope.WRITE, sid="w"))
    await manager.add_token("acct", _refresh_token(TokenScope.READ, sid="r"))
    client = TradeApiClient.from_account(
        "acct", accounts=manager, cache=MemoryAccessTokenCache(), http=_pool(seen), config=NO_PACING
    )
    assert seen == []  # nothing is read or exchanged at construction

    await client.http.request("GET", LIMITS)
    await client.http.request("POST", ORDERS, json={})
    await client.http.request("GET", PORTFOLIO)

    exchanges = [r.read().decode().split("&")[0] for r in seen if "keycloak" in r.url.path]
    calls = [r.headers["Authorization"] for r in seen if "keycloak" not in r.url.path]
    assert exchanges == ["client_id=trade-api-read", "client_id=trade-api-write"]
    assert calls == ["Bearer minted-read", "Bearer minted-write", "Bearer minted-read"]


async def test_from_account_names_the_account_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[httpx.Request] = []
    manager = AccountManager.from_file(tmp_path / "accounts.json")
    await manager.add_token("acct", _refresh_token(TokenScope.READ, sid="r"))
    monkeypatch.setenv("BACSY_ACCOUNT", "acct")

    client = TradeApiClient.from_account(
        accounts=manager, cache=MemoryAccessTokenCache(), http=_pool(seen), config=NO_PACING
    )
    await client.http.request("GET", LIMITS)

    assert seen[0].url.path.startswith("/trade-api-keycloak/")
    assert seen[-1].headers["Authorization"] == "Bearer minted-read"


async def test_from_account_ignores_the_refresh_token_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``BACSY_REFRESH_TOKEN`` neither supplies a name nor replaces the accounts file."""
    monkeypatch.setenv("BACSY_REFRESH_TOKEN", _refresh_token(TokenScope.READ, sid="env"))
    seen: list[httpx.Request] = []

    with pytest.raises(ConfigurationError, match="no account name given"):
        TradeApiClient.from_account(http=_pool(seen), config=NO_PACING)

    client = TradeApiClient.from_account("ghost", http=_pool(seen), config=NO_PACING)
    with pytest.raises(AccountNotFoundError, match="no account named 'ghost'"):
        await client.http.request("GET", LIMITS)

    assert seen == []


async def test_from_refresh_token_exchanges_before_first_request() -> None:
    seen: list[httpx.Request] = []
    value = _refresh_token(TokenScope.WRITE, sid="w")

    async with TradeApiClient.from_refresh_token(
        value, http=_pool(seen), cache=MemoryAccessTokenCache(), config=NO_PACING
    ) as c:
        await c.http.request("GET", LIMITS)
        await c.http.request("GET", LIMITS)

    assert seen[0].url.path.startswith("/trade-api-keycloak/")
    assert (
        seen[0].read()
        == f"client_id=trade-api-write&grant_type=refresh_token&refresh_token={value}".encode()
    )
    assert seen[1].headers["Authorization"] == "Bearer minted-write"
    assert len(seen) == 3


async def test_from_refresh_token_accepts_several_tokens() -> None:
    seen: list[httpx.Request] = []
    tokens = [_refresh_token(TokenScope.WRITE, sid="w"), _refresh_token(TokenScope.READ, sid="r")]

    client = TradeApiClient.from_refresh_token(
        tokens, http=_pool(seen), cache=MemoryAccessTokenCache(), config=NO_PACING
    )
    await client.http.request("GET", LIMITS)

    assert seen[0].read().startswith(b"client_id=trade-api-read&")


async def test_from_refresh_token_reads_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    read = _refresh_token(TokenScope.READ, sid="r")
    write = _refresh_token(TokenScope.WRITE, sid="w")
    monkeypatch.setenv("BACSY_REFRESH_TOKEN", f"{read}, \n{write}")
    seen: list[httpx.Request] = []

    client = TradeApiClient.from_refresh_token(
        http=_pool(seen), cache=MemoryAccessTokenCache(), config=NO_PACING
    )
    await client.http.request("GET", LIMITS)
    await client.http.request("POST", ORDERS, json={})

    exchanges = [r.read().decode().split("&")[0] for r in seen if "keycloak" in r.url.path]
    assert exchanges == ["client_id=trade-api-read", "client_id=trade-api-write"]


def test_from_refresh_token_without_a_token_anywhere_raises() -> None:
    with pytest.raises(ConfigurationError, match="no refresh token given") as info:
        TradeApiClient.from_refresh_token(http=_pool([]), config=NO_PACING)

    assert "BACSY_REFRESH_TOKEN" in str(info.value)


async def test_from_refresh_token_caches_access_tokens_in_the_state_directory(
    tmp_path: Path,
) -> None:
    """Two runs holding the same refresh token exchange it once, not once each."""
    seen: list[httpx.Request] = []
    value = _refresh_token(TokenScope.READ, sid="shared")

    for _ in range(2):
        client = TradeApiClient.from_refresh_token(value, http=_pool(seen), config=NO_PACING)
        await client.http.request("GET", LIMITS)

    assert [r for r in seen if "keycloak" in r.url.path] != []
    assert len([r for r in seen if "keycloak" in r.url.path]) == 1
    cache_file = tmp_path / "tokens.json"
    assert cache_file.exists()
    assert value not in cache_file.read_text()


async def test_an_injected_cache_keeps_access_tokens_off_disk(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    value = _refresh_token(TokenScope.READ, sid="shared")

    for _ in range(2):
        client = TradeApiClient.from_refresh_token(
            value, http=_pool(seen), cache=MemoryAccessTokenCache(), config=NO_PACING
        )
        await client.http.request("GET", LIMITS)

    assert len([r for r in seen if "keycloak" in r.url.path]) == 2
    assert not (tmp_path / "tokens.json").exists()


async def test_from_refresh_token_works_without_a_state_directory(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no resolvable state directory the cache falls back to memory."""
    for name in ("BACSY_STATE_DIR", "XDG_STATE_HOME", "LOCALAPPDATA", "HOME"):
        monkeypatch.delenv(name, raising=False)

    def _no_home() -> Path:
        msg = "Could not determine home directory."
        raise RuntimeError(msg)

    monkeypatch.setattr(Path, "home", staticmethod(_no_home))
    seen: list[httpx.Request] = []

    with caplog.at_level(logging.WARNING, logger="bacsy.auth"):
        client = TradeApiClient.from_refresh_token(
            _refresh_token(TokenScope.READ, sid="r"), http=_pool(seen), config=NO_PACING
        )
        await client.http.request("GET", LIMITS)

    assert seen[-1].headers["Authorization"] == "Bearer minted-read"
    assert [r.message for r in caplog.records].count(
        "no state directory available; caching access tokens in memory only"
    ) == 1


async def test_from_account_works_without_a_state_directory(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = AccountManager(AccountStore(tmp_path / "accounts.json"))
    await manager.add_token("main", _refresh_token(TokenScope.READ, sid="r"))
    for name in ("BACSY_STATE_DIR", "XDG_STATE_HOME", "LOCALAPPDATA", "HOME"):
        monkeypatch.delenv(name, raising=False)

    def _no_home() -> Path:
        msg = "Could not determine home directory."
        raise RuntimeError(msg)

    monkeypatch.setattr(Path, "home", staticmethod(_no_home))
    seen: list[httpx.Request] = []

    with caplog.at_level(logging.WARNING, logger="bacsy.auth"):
        client = TradeApiClient.from_account(
            "main", accounts=manager, http=_pool(seen), config=NO_PACING
        )
        await client.http.request("GET", LIMITS)

    assert seen[-1].headers["Authorization"] == "Bearer minted-read"
    assert [r.message for r in caplog.records].count(
        "no state directory available; caching access tokens in memory only"
    ) == 1


async def test_from_refresh_token_survives_an_unusable_state_directory(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A state directory that cannot be used costs one warning, not the request."""
    blocker = tmp_path / "blocker"
    blocker.write_text("")
    monkeypatch.setenv("BACSY_STATE_DIR", str(blocker))
    seen: list[httpx.Request] = []

    with caplog.at_level(logging.WARNING, logger="bacsy.auth"):
        client = TradeApiClient.from_refresh_token(
            _refresh_token(TokenScope.READ, sid="r"), http=_pool(seen), config=NO_PACING
        )
        await client.http.request("GET", LIMITS)
        await client.http.request("GET", LIMITS)

    assert seen[-1].headers["Authorization"] == "Bearer minted-read"
    assert len([r for r in seen if "keycloak" in r.url.path]) == 1
    assert len([r for r in caplog.records if "in memory only" in r.message]) == 1
    assert blocker.read_text() == ""


def test_undecodable_refresh_token_fails_at_construction() -> None:
    with pytest.raises(InvalidTokenError, match=r"refresh token \(") as info:
        TradeApiClient.from_refresh_token("not-a-token-at-all")

    assert "not-a-token-at-all" not in str(info.value)


def _pool(seen: list[httpx.Request]) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(_recording_handler(seen)), base_url="https://be.broker.ru"
    )
