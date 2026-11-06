"""天气解析的测试。全部用假的 HTTP 传输层，不联网。"""

from __future__ import annotations

import httpx
import pytest

from outfit.clients import weather

HOURS = [f"2026-11-06T{hour:02d}:00" for hour in range(24)]


def _payload(temps=None, codes=None, tmin=2.0, tmax=20.0):
    return {
        "hourly": {
            "time": HOURS,
            "temperature_2m": temps if temps is not None else [float(h) for h in range(24)],
            "weather_code": codes if codes is not None else [0] * 24,
        },
        "daily": {"temperature_2m_min": [tmin], "temperature_2m_max": [tmax]},
    }


def test_parse_takes_the_outdoor_hour():
    result = weather.parse(_payload(), outdoor_hour=8)
    assert result.hour_temp == 8.0
    assert result.outdoor_hour == 8


def test_effective_temperature_weights_morning_above_daily_low():
    result = weather.parse(_payload(tmin=2.0), outdoor_hour=8)
    # 0.6 × 8 + 0.4 × 2 = 5.6
    assert result.effective_c == pytest.approx(5.6)


def test_coldest_hour_drags_the_estimate_down():
    warm_morning = weather.parse(_payload(tmin=10.0), outdoor_hour=8)
    cold_morning = weather.parse(_payload(tmin=-2.0), outdoor_hour=8)
    assert cold_morning.effective_c < warm_morning.effective_c


def test_parse_rejects_empty_hourly():
    with pytest.raises(weather.WeatherError):
        weather.parse({"hourly": {"time": [], "temperature_2m": []}})


def test_condition_and_rain_flags():
    assert weather.condition_text(0) == "晴"
    assert weather.condition_text(61) == "小雨"
    assert weather.condition_text(9999) == "说不准"

    rainy = weather.parse(_payload(codes=[61] * 24))
    assert rainy.is_rainy and not rainy.is_snowy

    snowy = weather.parse(_payload(codes=[71] * 24))
    assert snowy.is_snowy and not snowy.is_rainy


def test_parse_survives_missing_daily_block():
    result = weather.parse({"hourly": {"time": HOURS, "temperature_2m": [5.0] * 24}})
    assert result.temp_min == 5.0
    assert result.temp_max == 5.0


def test_geocode_parses_city():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "geocoding" in str(request.url)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "name": "杭州",
                        "latitude": 30.29,
                        "longitude": 120.16,
                        "admin1": "浙江",
                        "country": "中国",
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    city = weather.geocode("杭州", client=client)
    assert city is not None
    assert city.name == "杭州"
    assert city.label == "浙江·杭州"
    assert city.latitude == pytest.approx(30.29)


def test_geocode_returns_none_for_unknown_place():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    assert weather.geocode("不存在的地方", client=client) is None


def test_geocode_raises_on_network_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(weather.WeatherError):
        weather.geocode("杭州", client=client)


def test_fetch_parses_full_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_payload(tmin=3.0, tmax=18.0, codes=[2] * 24))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    city = weather.City(name="杭州", latitude=30.29, longitude=120.16)
    result = weather.fetch(city, client=client)
    assert result.hour_temp == 8.0
    assert "3" in result.summary() and "18" in result.summary()
