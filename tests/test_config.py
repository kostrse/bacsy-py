"""Configuration defaults and derived values."""

from __future__ import annotations

import bacsy
from bacsy import DEFAULT_USER_AGENT, ClientConfig, RateLimitConfig
from bacsy.routes import Service


def test_rate_for_applies_safety_factor() -> None:
    assert RateLimitConfig().rate_for(Service.PORTFOLIO) == 9.0
    assert RateLimitConfig().rate_for(Service.NONTRADE_OPERATIONS) == 2.7


def test_rate_for_honours_overrides() -> None:
    config = RateLimitConfig(safety_factor=1.0, overrides={Service.PORTFOLIO: 2.0})

    assert config.rate_for(Service.PORTFOLIO) == 2.0
    assert config.rate_for(Service.LIMIT) == 10.0


def test_client_config_nests_policies() -> None:
    config = ClientConfig()

    assert config.retry.max_attempts == 3
    assert config.reconnect.max_attempts is None
    assert config.stream.overflow == "drop_oldest"


def test_client_config_defaults_to_library_user_agent() -> None:
    assert ClientConfig().user_agent == DEFAULT_USER_AGENT
    assert f"bacsy/{bacsy.__version__}" == DEFAULT_USER_AGENT
