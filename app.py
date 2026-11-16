import os
from datetime import date
from typing import Any

import requests
from flask import Flask, render_template, request
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from waitress import serve


app = Flask(__name__)
cache = Cache(app, config={
    "CACHE_TYPE": os.environ.get("CACHE_TYPE", "SimpleCache"),
    "CACHE_DEFAULT_TIMEOUT": 600,
    "CACHE_REDIS_URL": os.environ.get("CACHE_REDIS_URL", "redis://localhost:6379/0"),
})
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["120 per hour"],
    storage_uri=os.environ.get("RATELIMIT_STORAGE_URI", "memory://"),
)
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT = 8

WEATHER_DESCRIPTIONS = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}
FORECAST_DAYS = 5
CACHE_TIMEOUT = 600


class WeatherServiceError(Exception):
    pass


def _get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise WeatherServiceError("Weather provider request failed") from exc

    if not isinstance(payload, dict):
        raise WeatherServiceError("Weather provider returned an invalid response")
    if payload.get("error"):
        raise WeatherServiceError("Weather provider rejected the request")
    return payload


def _weather_icon(code: int, is_day: bool) -> str:
    if code == 0:
        return "☀️" if is_day else "🌙"
    if code in (1, 2, 3):
        return "🌤️" if is_day and code != 3 else "☁️"
    if code in (45, 48):
        return "🌫️"
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return "🌧️"
    if code in (71, 73, 75, 77, 85, 86):
        return "❄️"
    if code in (95, 96, 99):
        return "⛈️"
    return "🌡️"


def _weather_theme(code: int, is_day: bool) -> str:
    if code == 0:
        return "theme-clear-day" if is_day else "theme-clear-night"
    if code in (1, 2, 3):
        return "theme-cloudy"
    if code in (45, 48):
        return "theme-fog"
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return "theme-rain"
    if code in (71, 73, 75, 77, 85, 86):
        return "theme-snow"
    if code in (95, 96, 99):
        return "theme-storm"
    return "theme-default"


def _get_weather(
    latitude: float,
    longitude: float,
    location: dict[str, Any],
) -> dict[str, Any]:
    payload = _get_json(
        WEATHER_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": (
                "temperature_2m,relative_humidity_2m,apparent_temperature,"
                "is_day,weather_code,wind_speed_10m"
            ),
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max"
            ),
            "forecast_days": FORECAST_DAYS,
            "timezone": "auto",
        },
    )
    current = payload.get("current")
    if not isinstance(current, dict):
        raise WeatherServiceError("Weather provider returned incomplete conditions")

    required_fields = (
        "temperature_2m",
        "relative_humidity_2m",
        "apparent_temperature",
        "is_day",
        "weather_code",
        "wind_speed_10m",
    )
    if any(field not in current for field in required_fields):
        raise WeatherServiceError("Weather provider returned incomplete conditions")

    numeric_fields = (
        "temperature_2m",
        "relative_humidity_2m",
        "apparent_temperature",
        "wind_speed_10m",
    )
    if any(
        not isinstance(current[field], (int, float))
        or isinstance(current[field], bool)
        for field in numeric_fields
    ):
        raise WeatherServiceError("Weather provider returned invalid conditions")

    try:
        code = int(current["weather_code"])
        is_day_value = int(current["is_day"])
    except (TypeError, ValueError) as exc:
        raise WeatherServiceError("Weather provider returned invalid conditions") from exc
    if is_day_value not in (0, 1):
        raise WeatherServiceError("Weather provider returned invalid conditions")
    is_day = is_day_value == 1

    daily = payload.get("daily")
    daily_fields = (
        "time",
        "weather_code",
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_probability_max",
    )
    if not isinstance(daily, dict) or any(
        not isinstance(daily.get(field), list) or len(daily[field]) < FORECAST_DAYS
        for field in daily_fields
    ):
        raise WeatherServiceError("Weather provider returned incomplete forecast")

    forecast = []
    try:
        for index in range(FORECAST_DAYS):
            forecast_date = date.fromisoformat(daily["time"][index])
            daily_code = int(daily["weather_code"][index])
            high = daily["temperature_2m_max"][index]
            low = daily["temperature_2m_min"][index]
            precipitation = daily["precipitation_probability_max"][index]
            if not isinstance(high, (int, float)) or not isinstance(low, (int, float)):
                raise ValueError("Invalid daily temperature")
            if precipitation is not None and not isinstance(precipitation, (int, float)):
                raise ValueError("Invalid precipitation probability")
            forecast.append({
                "day": "Today" if index == 0 else forecast_date.strftime("%a"),
                "date": forecast_date.strftime("%b %d").replace(" 0", " "),
                "high": high,
                "low": low,
                "precipitation": precipitation,
                "description": WEATHER_DESCRIPTIONS.get(daily_code, "Current conditions"),
                "icon": _weather_icon(daily_code, True),
            })
    except (TypeError, ValueError) as exc:
        raise WeatherServiceError("Weather provider returned invalid forecast") from exc

    return {
        "name": location.get("name", "Your location"),
        "admin1": location.get("admin1"),
        "country": location.get("country"),
        "temperature": current["temperature_2m"],
        "humidity": current["relative_humidity_2m"],
        "feels_like": current["apparent_temperature"],
        "wind_speed": current["wind_speed_10m"],
        "description": WEATHER_DESCRIPTIONS.get(code, "Current conditions"),
        "icon": _weather_icon(code, is_day),
        "theme": _weather_theme(code, is_day),
        "timezone": payload.get("timezone"),
        "forecast": forecast,
    }


@cache.memoize(timeout=CACHE_TIMEOUT)
def get_city_weather(city_name: str) -> dict[str, Any] | None:
    locations = _get_json(
        GEOCODING_URL,
        {"name": city_name, "count": 1, "language": "en", "format": "json"},
    ).get("results")
    if not locations:
        return None
    if not isinstance(locations, list) or not isinstance(locations[0], dict):
        raise WeatherServiceError("Weather provider returned an invalid location")

    location = locations[0]
    latitude = location.get("latitude")
    longitude = location.get("longitude")
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        raise WeatherServiceError("Weather provider returned an invalid location")
    return _get_weather(latitude, longitude, location)


@cache.memoize(timeout=CACHE_TIMEOUT)
def get_coordinate_weather(latitude: float, longitude: float) -> dict[str, Any]:
    return _get_weather(
        latitude,
        longitude,
        {"name": "Your location"},
    )


@app.route("/", methods=["GET", "POST"])
@limiter.limit("30 per minute")
def index():
    city_query = request.args.get("city", "").strip()
    weather = None
    error = None
    status_code = 200

    if request.method == "POST":
        try:
            latitude = float(request.form.get("latitude", ""))
            longitude = float(request.form.get("longitude", ""))
        except ValueError:
            error = "Your location could not be read. Please try again."
            status_code = 400
        else:
            if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                error = "Your location coordinates are invalid."
                status_code = 400
            else:
                try:
                    weather = get_coordinate_weather(latitude, longitude)
                except WeatherServiceError:
                    app.logger.exception("Weather provider request failed")
                    error = "Weather data is temporarily unavailable. Please try again."
                    status_code = 502
    elif city_query:
        if len(city_query) > 100:
            error = "Please enter a city name under 100 characters."
            status_code = 400
        else:
            try:
                weather = get_city_weather(city_query)
                if weather is None:
                    error = f"We couldn't find “{city_query}”. Try another city."
                    status_code = 404
            except WeatherServiceError:
                app.logger.exception("Weather provider request failed")
                error = "Weather data is temporarily unavailable. Please try again."
                status_code = 502
    elif "city" in request.args:
        error = "Enter a city to see its current weather."
        status_code = 400

    return (
        render_template(
            "index.html",
            city_query=city_query,
            weather=weather,
            error=error,
        ),
        status_code,
    )


if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
