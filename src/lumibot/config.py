from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class QuoteToken(BaseModel):
    symbol: str
    address: str


class SourceSignalCfg(BaseModel):
    enabled: bool = True
    interval_sec: int = 5
    types: list[int] = Field(default_factory=lambda: [12, 20])

    @model_validator(mode="after")
    def ban_trenches_types(self) -> SourceSignalCfg:
        banned = {14, 15, 16}
        bad = banned.intersection(self.types)
        if bad:
            raise ValueError(f"signal types {sorted(bad)} are banned (trenches); use 12/20")
        return self


class SourceTrendingCfg(BaseModel):
    enabled: bool = True
    interval_sec: int = 20
    window: str = "1m"


class SourcesCfg(BaseModel):
    signal: SourceSignalCfg = Field(default_factory=SourceSignalCfg)
    trending: SourceTrendingCfg = Field(default_factory=SourceTrendingCfg)


class FiltersCfg(BaseModel):
    mc_min: float
    mc_max: float
    liquidity_min: float
    top10_max: float
    holders_min: float
    visiting_min: float
    max_mc_extension: float = 2.0
    enforce_mc_extension: bool = False


class SafetyThresholds(BaseModel):
    rug_max: float = 0.3
    bundler_max: float = 0.3
    rat_max: float = 0.3
    tax_max: float = 0.05


class CooldownCfg(BaseModel):
    same_type_min: int = 45
    cross_source_min: int = 15


class ExecLimits(BaseModel):
    max_notional_usd: float = 20
    daily_loss_usd: float = 50
    daily_trades: int = 10


class ExecutionCfg(BaseModel):
    mode: str = "paper"
    live_enabled: bool = False
    slippage_buy_pct: float = 0.05
    slippage_sell_pct: float = 0.05
    limits: ExecLimits = Field(default_factory=ExecLimits)


class ChainCfg(BaseModel):
    enabled: bool
    calibration_status: str
    safety_profile: str
    quote_tokens: list[QuoteToken] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    sources: SourcesCfg = Field(default_factory=SourcesCfg)
    filters: FiltersCfg
    safety: SafetyThresholds = Field(default_factory=SafetyThresholds)
    cooldown: CooldownCfg = Field(default_factory=CooldownCfg)
    execution: ExecutionCfg = Field(default_factory=ExecutionCfg)

    @model_validator(mode="after")
    def gate_enabled_calibrated(self) -> ChainCfg:
        if self.enabled and self.calibration_status != "calibrated":
            raise ValueError(
                f"chain enabled but calibration_status={self.calibration_status!r}; "
                "must be 'calibrated'"
            )
        return self


class RateLimitCfg(BaseModel):
    capacity: float = 20
    refill_per_sec: float = 6


class GlobalCfg(BaseModel):
    live_master_switch: bool = False
    rate_limit: RateLimitCfg = Field(default_factory=RateLimitCfg)
    enrichment_cache_ttl_sec: int = 300
    price_source: str = "token_info"


class StrategyCfg(BaseModel):
    notional_usd: float = 20
    hard_stop_pct: float = -0.50
    stage1_tp_pct: float = 0.30
    trail_drawdown_pct: float = 0.50
    timeout_hours: float = 4
    snapshots_sec: list[int] = Field(default_factory=lambda: [60, 300, 900, 3600])
    loss_cooldown_min: int = 180
    post_close_cooldown_min: int = 45


class AppConfig(BaseModel):
    global_: GlobalCfg = Field(alias="global")
    strategy: StrategyCfg = Field(default_factory=StrategyCfg)
    chains: dict[str, ChainCfg]

    model_config = {"populate_by_name": True}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gmgn_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_ids: str = ""
    lumibot_config: str = "config/chains.yaml"
    lumibot_db_path: str = "data/lumibot.db"
    lumibot_skip_ipv4_check: bool = False

    def chat_ids(self) -> list[int]:
        ids: list[int] = []
        for part in self.telegram_chat_ids.split(","):
            part = part.strip()
            if part:
                ids.append(int(part))
        return ids


def load_app_config(path: str | Path) -> AppConfig:
    raw = Path(path).read_text(encoding="utf-8")
    data: dict[str, Any] = yaml.safe_load(raw) or {}
    # Validate each enabled chain with a clear chain name
    chains = data.get("chains") or {}
    for name, cfg in chains.items():
        try:
            ChainCfg.model_validate(cfg)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"invalid config for chain {name}: {exc}") from exc
    return AppConfig.model_validate(data)


def enabled_chains(cfg: AppConfig) -> dict[str, ChainCfg]:
    return {k: v for k, v in cfg.chains.items() if v.enabled}
