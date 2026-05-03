"""Mock weather tool returning canned data."""

from __future__ import annotations

from capability.base import Tool

_MOCK_WEATHER: dict[str, dict] = {
    "tokyo": {"temp": 22, "condition": "Partly cloudy", "humidity": 60},
    "london": {"temp": 14, "condition": "Rainy", "humidity": 80},
    "new york": {"temp": 18, "condition": "Sunny", "humidity": 45},
    "paris": {"temp": 16, "condition": "Overcast", "humidity": 70},
    "sydney": {"temp": 25, "condition": "Clear", "humidity": 55},
}


class WeatherTool(Tool):
    """Return mock weather data for known cities."""

    @property
    def name(self) -> str:
        return "weather"

    @property
    def description(self) -> str:
        return "Get the current weather for a city."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name",
                }
            },
            "required": ["city"],
        }

    async def execute(self, **params) -> str:
        city = params.get("city", "").strip()
        if not city:
            return "Error: city is required"
        data = _MOCK_WEATHER.get(city.lower())
        if data is None:
            return f"No weather data available for '{city}'."
        return (
            f"Weather in {city}: {data['temp']}C, "
            f"{data['condition']}, humidity {data['humidity']}%"
        )
