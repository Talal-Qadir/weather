from datetime import datetime, timezone
from unittest.mock import Mock, patch
import requests
from django.test import SimpleTestCase
from .service import at_time, fetch_batch, WeatherError

class WeatherResponseTests(SimpleTestCase):
    def test_converts_offset_eta_to_utc_hour(self):
        eta=datetime.fromisoformat("2030-01-01T06:45:00+02:00")
        hourly={"time":["2030-01-01T04:00"],"wind_speed_10m":[25],"rain":[0.1],"snowfall":[None],"precipitation":[0.1],"temperature_2m":[31],"visibility":[1609.344]}
        result=at_time(1,2,eta,{"hourly":hourly,"forecast_issued_at":"2030-01-01T00:00:00Z"})
        self.assertTrue(result["available"]); self.assertEqual(result["forecast_time"],"2030-01-01T04:00Z"); self.assertEqual(result["wind_mph"],25); self.assertIsNone(result["snow_in_hr"])
        self.assertEqual(result["temperature_f"],31); self.assertEqual(result["visibility_miles"],1); self.assertEqual(result["forecast_issued_at"],"2030-01-01T00:00:00Z")
    def test_missing_forecast_is_explicitly_unavailable(self):
        result=at_time(1,2,datetime(2030,1,1,tzinfo=timezone.utc),{"hourly":{"time":[]}})
        self.assertFalse(result["available"]); self.assertIn("No hourly forecast",result["reason"])
    def test_outside_forecast_time_does_not_fabricate_values(self):
        result=at_time(1,2,datetime(2030,1,2,tzinfo=timezone.utc),{"hourly":{"time":["2030-01-01T00:00"]}})
        self.assertFalse(result["available"]); self.assertIsNone(result.get("wind_mph"))
    def test_out_of_horizon_api_response_is_unavailable_not_fabricated(self):
        response=Mock(status_code=400); response.raise_for_status.side_effect=requests.HTTPError("date outside forecast range")
        with patch("weather.service.requests.get",return_value=response):
            result=fetch_batch(((1.0,2.0),),"2030-01-01","horizon-test")
        self.assertEqual(result,[{"hourly":{}}])
    def test_weather_network_failure_is_reported(self):
        with patch("weather.service.requests.get",side_effect=requests.Timeout("timeout")):
            with self.assertRaises(WeatherError): fetch_batch(((1.0,2.0),),"2030-01-01","failure-test")
    def test_provider_request_includes_temperature_visibility_and_forecast_issue_time(self):
        response=Mock(status_code=200);response.json.return_value={"hourly":{"time":["2030-01-01T00:00"],"wind_speed_10m":[1],"rain":[0],"snowfall":[0],"precipitation":[0],"temperature_2m":[50],"visibility":[10000]}}
        with patch("weather.service.requests.get",return_value=response) as request:
            result=fetch_batch(((12.0,45.0),),"2030-01-01","extended-data-test")
        params=request.call_args.kwargs["params"]
        self.assertIn("temperature_2m",params["hourly"]);self.assertIn("visibility",params["hourly"])
        self.assertEqual(params["temperature_unit"],"fahrenheit")
        self.assertTrue(result[0]["forecast_issued_at"].endswith("Z"))
