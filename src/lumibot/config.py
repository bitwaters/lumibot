from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Chain -> required safety_profile binding, enforced at load time.
PROFILE_BY_CHAIN: dict[str, str] = {
    "sol": "sol_v1",
    "bsc": "evm_v1",
    "robinhood": "evm_v1",
}


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
    # Optional second trending loop (e.g. window=5m) run alongside `trending`.
    trending_5m: SourceTrendingCfg | None = None


class FiltersCfg(BaseModel):
    mc_min: float
    mc_max: float
    liquidity_min: float
    liquidity_ratio_min: float = 0.0   # liq/mc ratio; 0 = disabled
    top10_max: float
    holders_min: float
    visiting_min: float
    volume_1h_min: float = 0           # 0 = disabled
    volume_mc_ratio_min: float = 0     # volume_1h/mc ratio; 0 = disabled
    age_min_sec: int = 0    # reject tokens younger than this; 0 = disabled
    age_max_sec: int = 0    # reject tokens older than this; 0 = disabled
    max_mc_extension: float = 2.0
    enforce_mc_extension: bool = False
    # Chase gate: skip when the fresh quote price has run more than
    # chase_max_pct above the payload price (signal arrived too late, market
    # already pumped). Applied to both sources with one threshold per chain. 0 = disabled.
    chase_max_pct: float = 0.0


class SafetyThresholds(BaseModel):
    rug_max: float = 0.3
    bundler_max: float = 0.3
    rat_max: float = 0.3
    tax_max: float = 0.05
    # When True, missing (None) safety fields that would otherwise be tolerated
    # (e.g. sol_v1 honeypot) are treated as a hard fail instead of being ignored.
    strict_missing: bool = False


class CooldownCfg(BaseModel):
    same_type_min: int = 45
    cross_source_min: int = 15


class ExecLimits(BaseModel):
    max_notional_usd: float = 20
    daily_loss_usd: float = 50
    daily_trades: int = 10
    max_concurrent_positions: int = 0  # 0 = unlimited


class ExecutionCfg(BaseModel):
    mode: str = "paper"
    live_enabled: bool = False
    slippage_buy_pct: float = 0.05
    slippage_sell_pct: float = 0.05
    limits: ExecLimits = Field(default_factory=ExecLimits)


class StrategyCfg(BaseModel):
    notional_usd: float = 20
    hard_stop_pct: float = -0.30
    # Entry protection: tighter stop for the first early_stop_sec seconds after
    # open (relative to open_mark), then fall back to hard_stop_pct. 0 = disabled.
    early_stop_pct: float = 0.0
    early_stop_sec: int = 0
    # No-momentum exit: if within momentum_sec of open the price never rose
    # momentum_activate_pct above open_mark and now sits at/below
    # momentum_exit_pct, close immediately (fixed small loss instead of the
    # deeper early/hard stop). 0 = disabled.
    momentum_sec: int = 0
    momentum_activate_pct: float = 0.0
    momentum_exit_pct: float = 0.0
    stage1_tp_pct: float = 0.25
    trail_drawdown_pct: float = 0.30
    timeout_hours: float = 2
    stage1_sell_mode: str = "notional"  # notional | ratio
    stage1_sell_ratio: float = 0.50     # used when stage1_sell_mode == "ratio"
    snapshots_sec: list[int] = Field(default_factory=lambda: [60, 300, 900, 3600])
    loss_cooldown_min: int = 180
    post_close_cooldown_min: int = 45
    # Block re-opening ANY token sharing the same symbol for this many minutes
    # after a position closes (same-name duplicate pumps; address-keyed cooldowns
    # can't catch them). 0 = disabled.
    symbol_cooldown_min: int = 0
    # Pre-stage1 trail: protects unrealized profit if price pumps then dumps
    # before ever reaching stage1_tp_pct.
    pre_stage1_trail_enable: bool = False
    pre_stage1_trail_activate_pct: float = 0.15
    pre_stage1_trail_drawdown_pct: float = 0.40
    # Give a profitable (post-stage1) position extra runway before timing out.
    timeout_extend_if_profitable: bool = False
    timeout_extend_hours: float = 1.0
    # Tighten the post-stage1 trail drawdown as the peak/open_mark multiple grows.
    trail_dynamic: bool = True


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
    # Sole source of truth for exit/notional behaviour; each chain owns its own block.
    strategy: StrategyCfg

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
    # Minimum wall-clock seconds between GMGN requests (server default limit is
    # 1 req/s; bursts above this trip 429s/IP bans). 0 disables.
    min_interval_sec: float = 1.0


class CaQueryCfg(BaseModel):
    enabled: bool = True
    # Per-chat minimum interval between CA queries (anti-spam; protects quota).
    min_interval_sec: float = 5.0
    # Probe order for 0x (EVM) addresses among enabled chains.
    probe_order: list[str] = Field(default_factory=lambda: ["bsc", "robinhood"])


class NarrativeCfg(BaseModel):
    enabled: bool = False
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    # LLM request timeout (single-layer; covers the whole chat/completions call).
    timeout_sec: float = 10.0
    # Symbols shorter than this skip narrative inference.
    min_symbol_len: int = 1
    symbol_blocklist: list[str] = Field(default_factory=list)
    # Per-token narrative cache TTL; each token triggers at most one LLM call.
    cache_ttl_sec: int = 3600


class GlobalCfg(BaseModel):
    live_master_switch: bool = False
    rate_limit: RateLimitCfg = Field(default_factory=RateLimitCfg)
    enrichment_cache_ttl_sec: int = 300
    security_cache_ttl_sec: int = 3600
    price_source: str = "token_info"
    # Single-source-of-truth rules (config/chains.yaml) — no hardcoded rule knobs.
    manage_interval_sec: float = 5.0     # paper position manage loop interval
    dual_source_ttl_sec: float = 30.0    # dual-source sighting window
    alerts_per_chain: int = 5            # /alerts rows per chain
    trending_defer_budget: float = 4.0   # trending poll defers when limiter budget below this
    ca_query: CaQueryCfg | None = None
    narrative: NarrativeCfg | None = None


class AppConfig(BaseModel):
    global_: GlobalCfg = Field(alias="global")
    # Legacy-only: no longer read at runtime. Kept so old yaml files still parse;
    # load_app_config() strips this for compatibility and rejects chained configs without
    # per-chain strategy now (see PROFILE_BY_CHAIN / per-chain strategy validation).
    strategy: StrategyCfg | None = None
    chains: dict[str, ChainCfg]

    model_config = {"populate_by_name": True}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gmgn_api_key: str = ""
    telegram_bot_token: str = ""
    # Private (and optionally trusted) chats: receive pushes AND may run bot commands.
    telegram_chat_ids: str = ""
    # Push-only destinations (typically Telegram groups/supergroups, negative ids).
    # These receive signal/paper cards and may use read-only commands; /reset_paper stays private.
    telegram_group_chat_ids: str = ""
    lumibot_config: str = "config/chains.yaml"
    lumibot_db_path: str = "data/lumibot.db"
    lumibot_skip_ipv4_check: bool = False
    narrative_api_key: str = ""

    @staticmethod
    def _parse_id_list(raw: str, *, env_name: str) -> list[int]:
        ids: list[int] = []
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                ids.append(int(part))
            except ValueError as exc:
                raise ValueError(
                    f"invalid {env_name} entry {part!r}: expected a comma-separated "
                    "list of integer chat ids"
                ) from exc
        return ids

    def chat_ids(self) -> list[int]:
        """Command-authorized chats (also receive pushes)."""
        return self._parse_id_list(self.telegram_chat_ids, env_name="TELEGRAM_CHAT_IDS")

    def group_chat_ids(self) -> list[int]:
        """Push-only group/supergroup chats."""
        return self._parse_id_list(
            self.telegram_group_chat_ids, env_name="TELEGRAM_GROUP_CHAT_IDS"
        )

    def push_chat_ids(self) -> list[int]:
        """All destinations that receive signal/paper cards (control ∪ groups, deduped)."""
        seen: set[int] = set()
        out: list[int] = []
        for cid in [*self.chat_ids(), *self.group_chat_ids()]:
            if cid in seen:
                continue
            seen.add(cid)
            out.append(cid)
        return out


def load_app_config(path: str | Path) -> AppConfig:
    raw = Path(path).read_text(encoding="utf-8")
    data: dict[str, Any] = yaml.safe_load(raw) or {}

    if data.get("strategy") is not None:
        logger.warning(
            "config: top-level 'strategy' is deprecated and not used; "
            "define strategy under each chains.<name>.strategy block"
        )

    chains = data.get("chains") or {}
    for name, cfg in chains.items():
        if not isinstance(cfg, dict):
            raise ValueError(f"invalid config for chain {name}: expected a mapping")
        if cfg.get("strategy") is None:
            raise ValueError(
                f"invalid config for chain {name}: missing required 'strategy' block "
                "(chains.<name>.strategy) with per-chain strategy required"
            )
        try:
            chain_cfg = ChainCfg.model_validate(cfg)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"invalid config for chain {name}: {exc}") from exc

        expected_profile = PROFILE_BY_CHAIN.get(name)
        if expected_profile is not None and chain_cfg.safety_profile != expected_profile:
            raise ValueError(
                f"invalid config for chain {name}: safety_profile must be "
                f"{expected_profile!r} for this chain, got {chain_cfg.safety_profile!r}"
            )

    return AppConfig.model_validate(data)


def enabled_chains(cfg: AppConfig) -> dict[str, ChainCfg]:
    return {k: v for k, v in cfg.chains.items() if v.enabled}
