import os
from functools import lru_cache
from datetime import timezone
from datetime import datetime
import requests
class WeatherError(Exception): pass
@lru_cache(maxsize=128)
def fetch_batch(points, date, cache_bucket):
    base = os.getenv("OPEN_METEO_BASE_URL", "https://api.open-meteo.com/v1/forecast")
    params = {"latitude": ",".join(str(p[0]) for p in points), "longitude": ",".join(str(p[1]) for p in points), "hourly": "wind_speed_10m,precipitation,rain,snowfall,temperature_2m,visibility", "wind_speed_unit": "mph", "precipitation_unit": "inch", "temperature_unit": "fahrenheit", "timezone": "UTC", "start_date": date, "end_date": date}
    try:
        response = requests.get(base, params=params, timeout=18)
        if response.status_code==429: raise WeatherError("Weather forecast rate limit reached. Please wait and try again.")
        try: response.raise_for_status()
        except requests.HTTPError:
            if response.status_code == 400: return [{"hourly":{}} for _ in points]
            raise
        payload=response.json()
        results=payload if isinstance(payload,list) else [payload]
        issued_at=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
        for result in results:
            if isinstance(result,dict): result["forecast_issued_at"]=issued_at
        return results
    except (requests.RequestException, ValueError) as exc: raise WeatherError("Weather forecast service is unavailable. Please retry shortly.") from exc
def at_time(lat, lon, eta, data):
    hourly = data.get("hourly", {}); times = hourly.get("time", [])
    if not times: return {"available": False, "reason": "No hourly forecast was returned."}
    target = eta.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:00")
    try: index = times.index(target)
    except ValueError: return {"available": False, "reason": "Requested ETA is outside the provider forecast horizon."}
    def value(key):
        try: return float(hourly.get(key, [])[index]) if hourly[key][index] is not None else None
        except (IndexError, TypeError, ValueError, KeyError): return None
    visibility_m=value("visibility")
    return {"available": True, "forecast_time": target + "Z", "forecast_issued_at":data.get("forecast_issued_at"), "wind_mph": value("wind_speed_10m"), "rain_in_hr": value("rain"), "snow_in_hr": value("snowfall"), "precipitation_in": value("precipitation"), "temperature_f": value("temperature_2m"), "visibility_miles": visibility_m / 1609.344 if visibility_m is not None else None, "precipitation_note": "Rain and snow hourly accumulation are intensity proxies; instantaneous precipitation rate is not supplied."}
