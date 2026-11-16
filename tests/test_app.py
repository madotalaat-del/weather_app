import unittest
from unittest.mock import patch

import requests

from app import app, cache


class FakeResponse:
    def __init__(self, payload, status_error=None):
        self.payload = payload
        self.status_error = status_error

    def raise_for_status(self):
        if self.status_error:
            raise self.status_error

    def json(self):
        return self.payload


def forecast_payload():
    return {
        "timezone": "Africa/Cairo",
        "current": {
            "temperature_2m": 27.4,
            "relative_humidity_2m": 42,
            "apparent_temperature": 28.1,
            "is_day": 1,
            "weather_code": 0,
            "wind_speed_10m": 14,
        },
        "daily": {
            "time": [
                "2026-11-16",
                "2026-11-17",
                "2026-11-18",
                "2026-11-19",
                "2026-11-20",
            ],
            "weather_code": [0, 2, 61, 71, 95],
            "temperature_2m_max": [28, 27, 24, 19, 21],
            "temperature_2m_min": [18, 19, 17, 12, 14],
            "precipitation_probability_max": [0, 10, 70, 30, 45],
        },
    }


class WeatherAppTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        cache.clear()
        self.client = app.test_client()

    @patch("app.requests.get")
    def test_search_displays_current_weather_and_icon(self, get):
        get.side_effect = [
            FakeResponse({
                "results": [{
                    "name": "Cairo",
                    "admin1": "Cairo Governorate",
                    "country": "Egypt",
                    "latitude": 30.04,
                    "longitude": 31.24,
                }]
            }),
            FakeResponse(forecast_payload()),
        ]

        response = self.client.get("/?city=Cairo")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Cairo", response.data)
        self.assertIn(b"27", response.data)
        self.assertIn(b"Clear sky", response.data)
        self.assertIn("☀️".encode(), response.data)
        self.assertIn(b"5-day forecast", response.data)
        self.assertIn(b"28", response.data)
        self.assertIn(b"theme-clear-day", response.data)
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args.kwargs["timeout"], 8)
        self.assertEqual(get.call_args.kwargs["params"]["forecast_days"], 5)

    @patch("app.requests.get")
    def test_blank_city_shows_validation_message(self, get):
        response = self.client.get("/?city=%20%20")

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Enter a city", response.data)
        get.assert_not_called()

    @patch("app.requests.get")
    def test_unknown_city_has_distinct_message(self, get):
        get.return_value = FakeResponse({"results": []})

        response = self.client.get("/?city=NotARealCity")

        self.assertEqual(response.status_code, 404)
        self.assertIn(b"couldn&#39;t find", response.data)
        self.assertIn(b"Try another city", response.data)
        self.assertEqual(get.call_count, 1)

    @patch("app.requests.get")
    def test_provider_failure_shows_service_error(self, get):
        get.side_effect = requests.exceptions.Timeout("provider timed out")

        with self.assertLogs("app", level="ERROR") as logs:
            response = self.client.get("/?city=Cairo")

        self.assertEqual(response.status_code, 502)
        self.assertIn(b"temporarily unavailable", response.data)
        self.assertNotIn(b"provider timed out", response.data)
        self.assertIn("Weather provider request failed", logs.output[0])
        self.assertEqual(get.call_count, 1)

    @patch("app.requests.get")
    def test_browser_coordinates_show_local_weather_without_geocoding(self, get):
        get.return_value = FakeResponse(forecast_payload())

        response = self.client.post("/", data={"latitude": "30.04", "longitude": "31.24"})

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Your location", response.data)
        self.assertIn(b"Africa/Cairo", response.data)
        self.assertIn(b"Today", response.data)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.kwargs["params"]["latitude"], 30.04)
        self.assertEqual(get.call_args.kwargs["params"]["longitude"], 31.24)

    @patch("app.requests.get")
    def test_invalid_browser_coordinates_are_rejected(self, get):
        response = self.client.post("/", data={"latitude": "91", "longitude": "31"})

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"coordinates are invalid", response.data)
        get.assert_not_called()

    @patch("app.requests.get")
    def test_city_weather_response_is_cached(self, get):
        location = FakeResponse({
            "results": [{
                "name": "Cairo",
                "country": "Egypt",
                "latitude": 30.04,
                "longitude": 31.24,
            }]
        })
        get.side_effect = [location, FakeResponse(forecast_payload())]

        first = self.client.get("/?city=Cairo")
        second = self.client.get("/?city=Cairo")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(get.call_count, 2)

    def test_repeated_requests_are_rate_limited(self):
        address = {"REMOTE_ADDR": "192.0.2.77"}
        for _ in range(30):
            self.assertEqual(self.client.get("/", environ_base=address).status_code, 200)

        response = self.client.get("/", environ_base=address)

        self.assertEqual(response.status_code, 429)

    def test_heading_and_temperature_styles_are_white(self):
        response = self.client.get("/static/style.css")
        css = response.data.decode()

        self.assertEqual(response.status_code, 200)
        self.assertRegex(css, r"\.intro h1,\s*\.intro h1 span\s*\{\s*color:\s*#fff;")
        self.assertRegex(css, r"\.temperature\s*\{[^}]*color:\s*#fff;")


if __name__ == "__main__":
    unittest.main()
