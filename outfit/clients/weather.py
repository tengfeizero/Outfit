"""天气：Open-Meteo。免费、不用注册、不用密钥。

只做一件事：告诉你"早上出门那一刻大概多少度"。不做中长期预报，
因为穿搭决策只看出门那一刻。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 6.0

# WMO 天气代码 → 中文。只保留和穿衣有关的颗粒度。
_WMO = {
    0: "晴",
    1: "大致晴",
    2: "多云",
    3: "阴",
    45: "有雾",
    48: "雾凇",
    51: "小毛雨",
    53: "毛毛雨",
    55: "密毛雨",
    56: "冻毛雨",
    57: "冻毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "阵雨",
    81: "强阵雨",
    82: "暴雨",
    85: "阵雪",
    86: "强阵雪",
    95: "雷雨",
    96: "雷雨带冰雹",
    99: "强雷雨",
}

RAINY_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}
SNOWY_CODES = {71, 73, 75, 77, 85, 86}


class WeatherError(RuntimeError):
    """拿不到天气。调用方要能优雅降级，所以这里只抛统一异常。"""


@dataclass(frozen=True)
class City:
    name: str
    latitude: float
    longitude: float
    admin: str | None = None
    country: str | None = None

    @property
    def label(self) -> str:
        return f"{self.admin}·{self.name}" if self.admin and self.admin != self.name else self.name


@dataclass(frozen=True)
class Weather:
    hour_temp: float
    temp_min: float
    temp_max: float
    condition: str
    code: int
    outdoor_hour: int
    fetched_at: datetime

    @property
    def effective_c(self) -> float:
        """出门时的体感温度：出门那一刻为主，全天最低做修正。

        这么算的理由：早上八点的温度才决定你穿什么；但一天里最冷的那一刻
        决定你会不会后悔。六四开，比取平均更接近真实感受。
        """
        return round(0.6 * self.hour_temp + 0.4 * self.temp_min, 1)

    @property
    def is_rainy(self) -> bool:
        return self.code in RAINY_CODES

    @property
    def is_snowy(self) -> bool:
        return self.code in SNOWY_CODES

    def summary(self) -> str:
        return f"{self.condition} {self.temp_min:.0f}–{self.temp_max:.0f}℃"


def condition_text(code: int) -> str:
    return _WMO.get(code, "说不准")


def _client(client: httpx.Client | None) -> httpx.Client:
    return client or httpx.Client(timeout=TIMEOUT)


def geocode(name: str, client: httpx.Client | None = None) -> City | None:
    """城市名 → 坐标。找不到返回 None，不抛异常。"""
    name = name.strip()
    if not name:
        return None
    owns = client is None
    http = _client(client)
    try:
        response = http.get(
            GEOCODE_URL,
            params={"name": name, "count": 5, "language": "zh", "format": "json"},
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise WeatherError(f"查不到这个城市：{error}") from error
    finally:
        if owns:
            http.close()

    results = payload.get("results") or []
    if not results:
        return None

    top = results[0]
    return City(
        name=top.get("name") or name,
        latitude=float(top["latitude"]),
        longitude=float(top["longitude"]),
        admin=top.get("admin1"),
        country=top.get("country"),
    )


def fetch(city: City, client: httpx.Client | None = None, outdoor_hour: int = 8) -> Weather:
    owns = client is None
    http = _client(client)
    try:
        response = http.get(
            FORECAST_URL,
            params={
                "latitude": city.latitude,
                "longitude": city.longitude,
                "hourly": "temperature_2m,weather_code",
                "daily": "temperature_2m_min,temperature_2m_max",
                "timezone": "auto",
                "forecast_days": 1,
            },
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise WeatherError(f"取天气失败：{error}") from error
    finally:
        if owns:
            http.close()

    return parse(payload, outdoor_hour=outdoor_hour)


def parse(payload: dict, outdoor_hour: int = 8) -> Weather:
    """把 Open-Meteo 的响应解析成我们自己的结构。单独拆出来是为了能离线测。"""
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    temps = hourly.get("temperature_2m") or []
    codes = hourly.get("weather_code") or []

    if not times or not temps:
        raise WeatherError("天气数据里没有逐小时温度")

    index = _closest_hour(times, outdoor_hour)
    try:
        hour_temp = float(temps[index])
    except (TypeError, IndexError, ValueError) as error:
        raise WeatherError("逐小时温度不可用") from error

    daily = payload.get("daily") or {}
    mins = daily.get("temperature_2m_min") or []
    maxs = daily.get("temperature_2m_max") or []
    temp_min = float(mins[0]) if mins and mins[0] is not None else hour_temp
    temp_max = float(maxs[0]) if maxs and maxs[0] is not None else hour_temp

    code = 0
    if index < len(codes) and codes[index] is not None:
        code = int(codes[index])

    return Weather(
        hour_temp=hour_temp,
        temp_min=min(temp_min, hour_temp),
        temp_max=max(temp_max, hour_temp),
        condition=condition_text(code),
        code=code,
        outdoor_hour=outdoor_hour,
        fetched_at=datetime.now(timezone.utc),
    )


def _closest_hour(times: list[str], hour: int) -> int:
    """在逐小时时间轴里找最接近出门时刻的那一格。"""
    best_index = 0
    best_gap = None
    for index, stamp in enumerate(times):
        try:
            parsed = datetime.fromisoformat(stamp)
        except ValueError:
            continue
        gap = abs(parsed.hour - hour)
        if best_gap is None or gap < best_gap:
            best_gap = gap
            best_index = index
    return best_index
