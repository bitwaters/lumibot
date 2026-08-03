import pytest
from pydantic import ValidationError

from lumibot.config import ChainCfg, FiltersCfg


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
