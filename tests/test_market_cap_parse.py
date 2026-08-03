from lumibot.gmgn.client import _market_cap_from_info_dict, _price_from_info_dict


def test_market_cap_direct_field():
    assert _market_cap_from_info_dict({"market_cap": "125000", "price": "0.1"}) == 125000.0


def test_market_cap_derived_from_price_times_circulating_supply():
    info = {
        "price": {"price": "0.00012696133"},
        "circulating_supply": "978417668",
        "total_supply": "1000000000",
    }
    assert abs(_price_from_info_dict(info) - 0.00012696133) < 1e-12
    mc = _market_cap_from_info_dict(info)
    assert mc is not None
    assert abs(mc - 0.00012696133 * 978417668) < 1e-3


def test_market_cap_none_without_fields():
    assert _market_cap_from_info_dict({"price": {"price": "0.1"}}) is None
