import pytest
from pydantic import ValidationError

from lumibot.config import ChainCfg, FiltersCfg, load_app_config


def test_enabled_requires_calibrated():
    with pytest.raises(ValidationError):
        ChainCfg(
            enabled=True,
            calibration_status="draft",
            safety_profile="sol_v1",
            filters=FiltersCfg(
                mc_min=1,
                mc_max=2,
                liquidity_min=1,
                top10_max=0.3,
                holders_min=1,
                visiting_min=1,
            ),
        )


def test_load_app_config_enforces_profile_binding_and_per_chain_strategy():
    app = load_app_config("config/chains.yaml")
    assert app.chains["sol"].safety_profile == "sol_v1"
    assert app.chains["bsc"].safety_profile == "evm_v1"
    assert app.chains["robinhood"].safety_profile == "evm_v1"
    # Strategy is per-chain required; top-level strategy is not used at runtime.
    assert app.chains["sol"].strategy.notional_usd == 20
    assert app.strategy is None


def test_wrong_safety_profile_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
global:
  live_master_switch: false
  rate_limit: {capacity: 1, refill_per_sec: 1}
  enrichment_cache_ttl_sec: 60
  price_source: token_info
chains:
  sol:
    enabled: false
    calibration_status: draft
    safety_profile: evm_v1
    quote_tokens: []
    platforms: []
    sources:
      signal: {enabled: false, interval_sec: 5, types: [12]}
      trending: {enabled: false, interval_sec: 20, window: 1m}
    filters:
      mc_min: 1
      mc_max: 2
      liquidity_min: 1
      top10_max: 0.5
      holders_min: 1
      visiting_min: 1
    safety: {rug_max: 0.3, bundler_max: 0.3, rat_max: 0.3, tax_max: 0.05}
    cooldown: {same_type_min: 1, cross_source_min: 1}
    execution:
      mode: paper
      live_enabled: false
      slippage_buy_pct: 0.05
      slippage_sell_pct: 0.05
      limits: {max_notional_usd: 20, daily_loss_usd: 50, daily_trades: 10}
    strategy:
      notional_usd: 20
      hard_stop_pct: -0.3
      stage1_tp_pct: 0.25
      trail_drawdown_pct: 0.3
      timeout_hours: 2
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="safety_profile"):
        load_app_config(bad)


def test_global_rule_knobs_defaults_and_yaml_override():
    from lumibot.config import GlobalCfg

    g = GlobalCfg()
    assert g.manage_interval_sec == 5.0
    assert g.dual_source_ttl_sec == 30.0
    assert g.alerts_per_chain == 5
    assert g.trending_defer_budget == 4.0

    app = load_app_config("config/chains.yaml")
    assert app.global_.manage_interval_sec == 5.0
    assert app.global_.dual_source_ttl_sec == 30.0
    assert app.global_.alerts_per_chain == 5
    assert app.global_.trending_defer_budget == 4.0

    overridden = GlobalCfg(manage_interval_sec=7.0, trending_defer_budget=2.0)
    assert overridden.manage_interval_sec == 7.0
    assert overridden.trending_defer_budget == 2.0
