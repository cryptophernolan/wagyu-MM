"""Bot configuration — loaded from config/config.yaml + .env"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ExchangeConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    api_url: str = "https://api.hyperliquid-testnet.xyz"
    ws_url: str = "wss://api.hyperliquid-testnet.xyz/ws"
    asset: str = "XMR1"
    quote_asset: str = "USDC"
    price_tick_size: float = 0.01   # price rounding precision (XMR1=0.01, PURR=0.0001)
    size_step: float = 0.01         # size rounding precision (XMR1=0.01, PURR=1.0)
    kraken_symbol: str = "XMR/USDT" # Kraken reference pair; set to "" to disable Kraken feed
    # base_coin: actual token name for balance lookup. Auto-derived from asset if empty.
    # Required for non-canonical markets like "@1035" (HYPE/USDC) where asset != token name.
    base_coin: str = ""


class TradingConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    cycle_interval_seconds: float = 2.0
    order_levels: int = 3
    level_sizes: list[float] = Field(default_factory=lambda: [50.0, 100.0, 200.0])


class AlgorithmConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    name: str = "avellaneda_stoikov"


class AvellanedaStoikovConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    gamma_calm: float = 0.04
    gamma_volatile: float = 0.08


class SpreadConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    calm_spread_bps: float = 8.0
    volatile_spread_bps: float = 25.0
    level_spacing_bps: float = 4.0


class InventoryConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    max_position_xmr: float = 10.0
    skew_factor: float = 0.5
    target_position_xmr: float = 0.0


class RiskConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    daily_loss_limit_usdc: float = 50.0
    max_drawdown_pct: float = 5.0
    stale_feed_seconds: float = 5.0


class VolatilityConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    window_minutes: int = 30
    calm_threshold_bps: float = 20.0
    volatile_threshold_bps: float = 35.0


class EnvConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    hl_private_key: str = ""
    hl_wallet_address: str = ""
    log_level: str = "INFO"
    env: str = "development"


class AppConfig:
    """Top-level application config assembled from YAML + env."""

    def __init__(
        self,
        exchange: ExchangeConfig,
        trading: TradingConfig,
        algorithm: AlgorithmConfig,
        avellaneda_stoikov: AvellanedaStoikovConfig,
        spread: SpreadConfig,
        inventory: InventoryConfig,
        risk: RiskConfig,
        volatility: VolatilityConfig,
        env: EnvConfig,
    ) -> None:
        self.exchange = exchange
        self.trading = trading
        self.algorithm = algorithm
        self.avellaneda_stoikov = avellaneda_stoikov
        self.spread = spread
        self.inventory = inventory
        self.risk = risk
        self.volatility = volatility
        self.env = env


def load_config(config_path: str = "config/config.yaml") -> AppConfig:
    """Load configuration from YAML file and environment variables."""
    path = Path(config_path)
    raw: dict[str, Any] = {}

    if not path.exists():
        example = Path("config/config.example.yaml")
        if example.exists():
            shutil.copy(example, path)
            with open(path) as f:
                raw = yaml.safe_load(f) or {}
        # else raw stays as empty dict — all defaults will be used
    else:
        with open(path) as f:
            raw = yaml.safe_load(f) or {}

    env_cfg = EnvConfig()

    return AppConfig(
        exchange=ExchangeConfig(**raw.get("exchange", {})),
        trading=TradingConfig(**raw.get("trading", {})),
        algorithm=AlgorithmConfig(**raw.get("algorithm", {})),
        avellaneda_stoikov=AvellanedaStoikovConfig(**raw.get("avellaneda_stoikov", {})),
        spread=SpreadConfig(**raw.get("spread", {})),
        inventory=InventoryConfig(**raw.get("inventory", {})),
        risk=RiskConfig(**raw.get("risk", {})),
        volatility=VolatilityConfig(**raw.get("volatility", {})),
        env=env_cfg,
    )
