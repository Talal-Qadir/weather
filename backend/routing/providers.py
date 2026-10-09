import os, math, requests, logging, re, time
from functools import lru_cache
class ProviderError(Exception):
    def __init__(self, message, status_code=503):
        super().__init__(message)
        self.status_code = status_code
logger = logging.getLogger(__name__)

def _provider_detail(response, secret):
    """Return a short provider message safe for logs; never log request data."""
    try:
        payload = response.json()
    except (ValueError, requests.RequestException):
        payload = None
    detail = ""
    if isinstance(payload, dict):
        error = payload.get("error", payload)
        if isinstance(error, dict):
            detail = str(error.get("message") or error.get("description") or error.get("code") or "")
        elif isinstance(error, str):
            detail = error
    detail = re.sub(r"[\r\n\t\x00-\x1f]+", " ", detail).strip()
    if secret:
        detail = detail.replace(secret, "[redacted]")
    return detail[:400] or "Provider returned no error details."
@lru_cache(maxsize=256)
def geocode(query):
    key=os.getenv("OPENROUTESERVICE_API_KEY")
    if not key: raise ProviderError("Geocoding is not configured. Add OPENROUTESERVICE_API_KEY to backend/.env.")
    base=os.getenv("HEIGIT_API_BASE_URL","https://api.heigit.org").rstrip("/")
    try:
        r=requests.get(base+"/pelias/v1/search",params={"text":query,"size":8,"api_key":key},timeout=12)
        if r.status_code==429: raise ProviderError("Place search rate limit reached. Please wait and try again.")
        r.raise_for_status(); payload=r.json(); features=payload.get("features",[]) if isinstance(payload,dict) else []
        results=[]
        for feature in features:
            try:
                coords=feature["geometry"]["coordinates"]; props=feature.get("properties",{}); label=props.get("label") or props.get("name")
                lon,lat=float(coords[0]),float(coords[1])
                if label and -90<=lat<=90 and -180<=lon<=180:
                    results.append({"label":label,"lat":lat,"lon":lon,"locality":props.get("locality") or props.get("localadmin") or props.get("county"),"region":props.get("region"),"country":props.get("country"),"postalcode":props.get("postalcode")})
            except (KeyError,TypeError,ValueError,IndexError): continue
        return results
    except ProviderError: raise
    except (requests.RequestException, ValueError) as exc: raise ProviderError("Place search service is unavailable. Check the HeiGIT API key and try again.") from exc
def _decode_flexible_polyline(encoded):
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    cursor = 0

    def read_unsigned():
        nonlocal cursor
        result = shift = 0
        while cursor < len(encoded):
            value = alphabet.find(encoded[cursor])
            cursor += 1
            if value < 0:
                raise ValueError("Invalid HERE polyline encoding")
            result |= (value & 0x1F) << shift
            if value < 0x20:
                return result
            shift += 5
        raise ValueError("Truncated HERE polyline encoding")

    def read_signed():
        value = read_unsigned()
        return ~(value >> 1) if value & 1 else value >> 1

    version = read_unsigned()
    if version != 1:
        raise ValueError("Unsupported HERE polyline version")
    precision = read_unsigned()
    third_dimension = read_unsigned()
    third_precision = read_unsigned()
    factor = 10 ** precision
    third_factor = 10 ** third_precision
    lat = lon = z = 0
    points = []
    while cursor < len(encoded):
        lat += read_signed()
        lon += read_signed()
        if third_dimension:
            z += read_signed()
        points.append([lat / factor, lon / factor])
    return points


def _parse_here_routes(payload, name):
    routes = []
    for item in payload.get("routes", []) if isinstance(payload, dict) else []:
        sections = item.get("sections", [])
        geometry = []
        distance = duration = 0.0
        has_non_road_section = False
        try:
            for section in sections:
                transport = section.get("transport", {})
                if str(section.get("type", "")).lower() in {"transit", "ferry"} or str(transport.get("mode", "")).lower() == "ferry":
                    has_non_road_section = True
                    break
                summary = section["summary"]
                distance += float(summary["length"])
                duration += float(summary["duration"])
                part = _decode_flexible_polyline(section["polyline"])
                if geometry and part and haversine(geometry[-1], part[0]) < 0.001:
                    part = part[1:]
                geometry.extend(part)
            if has_non_road_section or len(geometry) < 2 or distance <= 0 or duration <= 0:
                continue
            if any(not (-90 <= lat <= 90 and -180 <= lon <= 180) for lat, lon in geometry):
                continue
            routes.append({"id": "", "name": name, "geometry": geometry, "distance_miles": distance / 1609.344, "duration_seconds": duration, "provider": "here"})
        except (KeyError, TypeError, ValueError, IndexError):
            continue
    return routes


def directions(origin, destination, departure):
    ors_key = os.getenv("OPENROUTESERVICE_API_KEY")
    here_key = os.getenv("HERE_ROUTING_API_KEY")
    if not ors_key and not here_key:
        raise ProviderError("Routing is not configured. Add OPENROUTESERVICE_API_KEY or HERE_ROUTING_API_KEY to backend/.env.")

    timeout = float(os.getenv("OPENROUTESERVICE_TIMEOUT_SECONDS", "15"))
    collected = []
    failures = []
    ors_rate_limited = False
    ors_stop_strategies = False
    here_rate_limited = False

    def distinct_from_existing(candidate):
        """Reject the same road path even where providers encode it differently."""
        points = candidate["geometry"]
        if len(points) < 2:
            return False

        def normalized_samples(geometry, count=25):
            lengths = [haversine(a, b) for a, b in zip(geometry, geometry[1:])]
            total = sum(lengths)
            if total <= 0:
                return geometry[:1] * count
            samples = []
            for fraction in (i / (count - 1) for i in range(count)):
                target = total * fraction
                walked = 0.0
                for index, segment in enumerate(lengths):
                    if walked + segment >= target or index == len(lengths) - 1:
                        ratio = 0.0 if segment == 0 else (target - walked) / segment
                        a, b = geometry[index], geometry[index + 1]
                        samples.append((a[0] + (b[0] - a[0]) * ratio, a[1] + (b[1] - a[1]) * ratio))
                        break
                    walked += segment
            return samples

        sample = normalized_samples(points)
        for existing in collected:
            other = normalized_samples(existing["geometry"])
            max_offset = max(haversine(a, b) for a, b in zip(sample, other))
            distance_delta = abs(candidate["distance_miles"] - existing["distance_miles"])
            duration_delta = abs(candidate["duration_seconds"] - existing["duration_seconds"])
            if max_offset <= 0.08 and distance_delta <= max(0.5, existing["distance_miles"] * 0.005) and duration_delta <= max(120, existing["duration_seconds"] * 0.02):
                return False
        return True

    def collect(candidates):
        for candidate in candidates:
            if len(collected) >= 3:
                break
            if distinct_from_existing(candidate):
                candidate["id"] = f"route-{len(collected) + 1}"
                collected.append(candidate)

    def classify_provider_error(response, provider, secret, request_body=None):
        detail = _provider_detail(response, secret)
        logger.warning("%s routing response status=%s detail=%s", provider, response.status_code, detail)
        lowered = detail.lower()
        if response.status_code == 429:
            return ProviderError(f"{provider} routing rate limit reached. Please wait and retry.", status_code=429)
        if response.status_code in (502, 503, 504):
            return ProviderError(f"{provider} routing is temporarily unavailable (HTTP {response.status_code}). Please try again shortly.")
        if provider == "HeiGIT" and response.status_code == 400 and ("approximated route distance" in lowered or "maximum distance" in lowered or "route distance limit" in lowered or "distance must not be greater" in lowered):
            if request_body and "alternative_routes" in request_body:
                return ProviderError("HeiGIT declined this alternative-routing strategy because of its hosted-service distance limits.", status_code=400)
            return ProviderError("HeiGIT's hosted service could not calculate this route distance; attempting the configured secondary routing provider.", status_code=400)
        if provider == "HeiGIT" and response.status_code == 400 and ("route could not be found" in lowered or "unable to find a route" in lowered):
            return ProviderError("HeiGIT found no connected road route; attempting the configured secondary routing provider.", status_code=422)
        return ProviderError(f"{provider} routing returned HTTP {response.status_code}: {detail}", status_code=400 if response.status_code == 400 else 502)

    def request_ors(request_body):
        nonlocal ors_rate_limited, ors_stop_strategies
        profile = os.getenv("OPENROUTESERVICE_PROFILE", "driving-hgv")
        base = os.getenv("HEIGIT_API_BASE_URL", "https://api.heigit.org").rstrip("/")
        url = f"{base}/openrouteservice/v2/directions/{profile}/geojson"
        for attempt in range(2):
            try:
                response = requests.post(url, json=request_body, headers={"Authorization": ors_key, "Content-Type": "application/json"}, timeout=timeout)
                if response.status_code >= 400:
                    error = classify_provider_error(response, "HeiGIT", ors_key, request_body)
                    if error.status_code == 429:
                        ors_rate_limited = True
                    elif response.status_code in (502, 503, 504) and attempt == 0:
                        time.sleep(0.5)
                        continue
                    elif response.status_code >= 500:
                        ors_stop_strategies = True
                    elif response.status_code == 400 and "hosted service could not calculate this route distance" in str(error).lower():
                        ors_stop_strategies = True
                    raise error
                payload = response.json()
                if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
                    raise ProviderError("HeiGIT returned an invalid route response.")
                routes = []
                for feature in payload["features"][:3]:
                    try:
                        summary = feature["properties"]["summary"]
                        coords = feature["geometry"]["coordinates"]
                        distance, duration = float(summary["distance"]), float(summary["duration"])
                        geometry = [[float(c[1]), float(c[0])] for c in coords if len(c) >= 2]
                        if len(geometry) < 2 or distance <= 0 or duration <= 0 or any(not (-90 <= lat <= 90 and -180 <= lon <= 180) for lat, lon in geometry):
                            continue
                        routes.append({"id": "", "name": "HeiGIT route", "geometry": geometry, "distance_miles": distance / 1609.344, "duration_seconds": duration, "provider": "openrouteservice"})
                    except (KeyError, TypeError, ValueError, IndexError):
                        continue
                if not routes:
                    raise ProviderError("HeiGIT returned no connected, usable road route.", status_code=422)
                return routes
            except ProviderError as exc:
                failures.append(exc)
                # A provider's overall distance limit should switch to HERE promptly.
                if "attempting the configured secondary" in str(exc).lower():
                    return []
                return []
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt == 0:
                    time.sleep(0.5)
                    continue
                logger.warning("HeiGIT routing request failed (%s)", type(exc).__name__)
                failures.append(ProviderError(f"HeiGIT routing timed out or could not be reached after {timeout:g} seconds."))
                return []
            except requests.RequestException as exc:
                logger.warning("HeiGIT routing request failed (%s)", type(exc).__name__)
                failures.append(ProviderError("HeiGIT routing request failed. Check its API key, profile, or request configuration."))
                return []
            except ValueError as exc:
                failures.append(ProviderError("HeiGIT returned an invalid response. Please try again."))
                return []
        return []

    def request_here(routing_mode, alternatives):
        nonlocal here_rate_limited
        if not here_key:
            return []
        here_timeout = float(os.getenv("HERE_ROUTING_TIMEOUT_SECONDS", "20"))
        params = {
            "origin": f"{origin['lat']},{origin['lon']}",
            "destination": f"{destination['lat']},{destination['lon']}",
            "transportMode": "truck",
            "routingMode": routing_mode,
            "alternatives": min(2, max(0, alternatives)),
            "return": "polyline,summary",
            "avoid[features]": "ferry",
            "departureTime": departure.isoformat(),
            "apiKey": here_key,
        }
        for attempt in range(2):
            try:
                response = requests.get("https://router.hereapi.com/v8/routes", params=params, timeout=here_timeout)
                if response.status_code >= 400:
                    error = classify_provider_error(response, "HERE", here_key)
                    if response.status_code == 429:
                        here_rate_limited = True
                    if response.status_code in (502, 503, 504) and attempt == 0:
                        time.sleep(0.5)
                        continue
                    failures.append(error)
                    return []
                payload = response.json()
                parsed = _parse_here_routes(payload, f"HERE {routing_mode} route")
                if not parsed:
                    failures.append(ProviderError("HERE returned no continuous road-only truck route.", status_code=422))
                return parsed
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt == 0:
                    time.sleep(0.5)
                    continue
                logger.warning("HERE routing request failed (%s)", type(exc).__name__)
                failures.append(ProviderError(f"HERE routing timed out or could not be reached after {here_timeout:g} seconds."))
                return []
            except (requests.RequestException, ValueError, TypeError) as exc:
                logger.warning("HERE routing response failed (%s)", type(exc).__name__)
                failures.append(ProviderError("HERE returned an invalid route response."))
                return []
        return []

    if ors_key:
        # Ferry legs are multimodal transport, not continuous truck-driving routes.
        body = {"coordinates": [[origin["lon"], origin["lat"]], [destination["lon"], destination["lat"]]], "instructions": False, "geometry_simplify": False, "preference": "recommended", "options": {"avoid_features": ["ferries"]}}
        collect(request_ors(body))
        if not ors_rate_limited and not ors_stop_strategies and len(collected) < 3:
            collect(request_ors({**body, "alternative_routes": {"target_count": 3, "share_factor": 0.6, "weight_factor": 1.4}}))
        for preference in ("fastest", "shortest"):
            if len(collected) >= 3 or ors_rate_limited or ors_stop_strategies:
                break
            collect(request_ors({**body, "preference": preference}))
        if len(collected) < 3 and not ors_rate_limited and not ors_stop_strategies:
            collect(request_ors({**body, "options": {"avoid_features": ["tollways", "ferries"]}}))

    # HERE is a global-capable, truck-specific secondary. Its API supports up to
    # six alternatives, fast/short truck modes, and explicit ferry avoidance.
    if here_key and len(collected) < 3 and not here_rate_limited:
        collect(request_here("fast", 2))
        if len(collected) < 3 and not here_rate_limited:
            collect(request_here("short", 2))

    if not collected:
        if not here_key and any("attempting the configured secondary" in str(error).lower() for error in failures):
            raise ProviderError("HeiGIT cannot route this journey distance. Configure HERE_ROUTING_API_KEY to enable the secondary global truck-routing provider.", status_code=400)
        no_road = any(error.status_code == 422 for error in failures)
        if no_road:
            raise ProviderError("No continuous truck-driving road route is available between these locations. Flights, ferries, and shipping are outside this driving calculation.", status_code=422)
        if failures:
            raise failures[-1]
        raise ProviderError("No routing provider returned a usable road route.")
    if len(collected) < 3:
        count = len(collected)
        collected[0]["_alternatives_note"] = f"{count} distinct route{'s' if count != 1 else ''} {'are' if count != 1 else 'is'} available for this journey."
    return collected
def haversine(a,b):
    lat1,lon1=map(math.radians,a); lat2,lon2=map(math.radians,b); dlat,dlon=lat2-lat1,lon2-lon1
    return 3958.7613*2*math.asin(math.sqrt(math.sin(dlat/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2))
def sample_line(coords, spacing):
    if not coords: return []
    pts=[(coords[0][0],coords[0][1],0.0)]; cumulative=0.0; next_at=spacing
    for a,b in zip(coords,coords[1:]):
        segment=haversine(a,b)
        if segment<=0: continue
        while next_at<cumulative+segment:
            f=(next_at-cumulative)/segment; pts.append((a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f,next_at)); next_at+=spacing
        cumulative+=segment
    if cumulative>pts[-1][2]+.01: pts.append((coords[-1][0],coords[-1][1],cumulative))
    return pts
