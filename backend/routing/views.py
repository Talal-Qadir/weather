import os
import math
from datetime import timedelta, timezone as dt_timezone
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .serializers import AnalyzeSerializer
from .providers import geocode as lookup_places, directions, sample_line, ProviderError
from weather.service import at_time, fetch_batch, WeatherError
from risk_engine.engine import assess, LEVELS

def batch_weather(points):
    groups={}
    for cp in points:
        utc_eta=cp["eta"].astimezone(dt_timezone.utc)
        key=(round(cp["lat"],3),round(cp["lon"],3))
        cp["weather_key"]=(key,utc_eta.strftime("%Y-%m-%d"))
        groups.setdefault(utc_eta.strftime("%Y-%m-%d"),{})[key]=None
    forecasts={}
    for day,locations in groups.items():
        keys=list(locations)
        for start in range(0,len(keys),50):
            batch=keys[start:start+50]
            cache_bucket=timezone.now().astimezone(dt_timezone.utc).strftime("%Y%m%d%H")
            values=fetch_batch(tuple(batch),day,cache_bucket)
            for key,value in zip(batch,values): forecasts[(key,day)]=value
    return [at_time(cp["lat"],cp["lon"],cp["eta"],forecasts.get(cp["weather_key"],{})) for cp in points]

@api_view(["GET"])
def health(request): return Response({"status":"ok"})

@api_view(["GET"])
def config_status(request):
    return Response({"routing_configured": bool(os.getenv("OPENROUTESERVICE_API_KEY") or os.getenv("HERE_ROUTING_API_KEY")), "secondary_routing_configured": bool(os.getenv("HERE_ROUTING_API_KEY")), "weather_provider":"Open-Meteo", "geocoding_provider":"HeiGIT Pelias", "routing_provider":"HeiGIT openrouteservice with HERE truck-routing fallback", "routing_profile":os.getenv("OPENROUTESERVICE_PROFILE","driving-hgv")})

@api_view(["GET"])
def geocode(request):
    query=request.query_params.get("q", "").strip()
    if len(query)<3: return Response({"error":{"code":"invalid_query","message":"Enter at least 3 characters."}},status=400)
    try: return Response({"results":lookup_places(query)})
    except ProviderError as exc: return Response({"error":{"code":"geocoding_unavailable","message":str(exc)}},status=503)

@api_view(["POST"])
def analyze(request):
    serializer=AnalyzeSerializer(data=request.data)
    if not serializer.is_valid(): return Response({"error":{"code":"validation_error","message":"Check the journey details.","fields":serializer.errors}},status=400)
    data=serializer.validated_data
    try:
        if data.get("origin_place") and data.get("destination_place"):
            a,b=data["origin_place"],data["destination_place"]
        else:
            origins=lookup_places(data["origin"]); destinations=lookup_places(data["destination"])
            if not origins or not destinations: return Response({"error":{"code":"place_not_found","message":"Could not find the origin or destination. Choose a valid place from search suggestions."}},status=422)
            a,b=origins[0],destinations[0]
        for place in (a,b):
            if not math.isfinite(place["lat"]) or not math.isfinite(place["lon"]) or not (-90<=place["lat"]<=90 and -180<=place["lon"]<=180):
                return Response({"error":{"code":"invalid_location","message":"The selected location has invalid coordinates. Choose another place suggestion."}},status=400)
        if abs(a["lat"]-b["lat"])<1e-6 and abs(a["lon"]-b["lon"])<1e-6:
            return Response({"error":{"code":"same_location","message":"Choose different origin and destination locations."}},status=400)
        routes=directions(a,b,data["departure"])
        alternatives_note=routes[0].pop("_alternatives_note",None) if routes else None
    except ProviderError as exc:
        return Response({"error":{"code":"provider_error","message":str(exc)}},status=exc.status_code)
    try:
        for route in routes:
            route["arrival"]=(data["departure"]+timedelta(seconds=route["duration_seconds"])).isoformat()
            checkpoints=[]; checkpoint_points=[]
            for i,(lat,lon,miles) in enumerate(sample_line(route["geometry"],data["interval_miles"])):
                fraction=miles/route["distance_miles"] if route["distance_miles"] else 0
                eta=data["departure"]+timedelta(seconds=route["duration_seconds"]*fraction)
                checkpoint_points.append({"id":f"{route['id']}-cp-{i+1}","lat":lat,"lon":lon,"distance_miles":round(miles,1),"eta":eta})
            weather_values=batch_weather(checkpoint_points)
            for i,(cp,wx) in enumerate(zip(checkpoint_points,weather_values)):
                risk=assess(wx if wx.get("available") else {},data["load_lb"])
                checkpoints.append({**cp,"eta":cp["eta"].isoformat(),"weather":wx,"risk":risk})
            route["checkpoints"]=checkpoints
            bins={name:0.0 for name in LEVELS}; weighted_score=0.0; scored_miles=0.0
            for cp in checkpoints:
                level=cp["risk"]["overall_risk"]
                segment_miles=min(data["interval_miles"],max(0,route["distance_miles"]-cp["distance_miles"]))
                if level in bins: bins[level]+=segment_miles
                if level in LEVELS and segment_miles>0:
                    weighted_score+=LEVELS[level]*segment_miles; scored_miles+=segment_miles
            forecast_times=[c["weather"]["forecast_time"] for c in checkpoints if c["weather"].get("forecast_time")]
            route["summary"]={"checkpoint_count":len(checkpoints),"no_travel_miles":round(bins["No Travel"],1),"severe_miles":round(bins["Severe"],1),"high_miles":round(bins["High"],1),"moderate_miles":round(bins["Moderate"],1),"low_miles":round(bins["Low"],1),"no_travel_locations":[{"lat":c["lat"],"lon":c["lon"],"distance_miles":c["distance_miles"],"eta":c["eta"]} for c in checkpoints if c["risk"]["no_travel"]],"average_risk_score":round(weighted_score/scored_miles,2) if scored_miles else None,"weather_available":sum(1 for c in checkpoints if c["weather"].get("available")),"forecast_timezone":"UTC","forecast_start":min(forecast_times) if forecast_times else None,"forecast_end":max(forecast_times) if forecast_times else None,"overall_risk":max((c["risk"]["overall_risk"] for c in checkpoints if c["risk"]["overall_risk"] in LEVELS),key=lambda v:LEVELS[v],default="Unavailable")}
        routes.sort(key=lambda r:(r["summary"]["severe_miles"],r["summary"]["high_miles"],r["summary"]["average_risk_score"] if r["summary"]["average_risk_score"] is not None else 999,r["duration_seconds"]))
        for idx,route in enumerate(routes): route["rank"]=idx+1; route["recommended"]=idx==0
    except WeatherError as exc:
        return Response({"error":{"code":"weather_unavailable","message":str(exc)}},status=503)
    count_note = None if len(routes) == 3 else f"{len(routes)} distinct route{'s' if len(routes) != 1 else ''} {'are' if len(routes) != 1 else 'is'} available for this journey."
    return Response({"routes":routes,"recommended_route_id":routes[0]["id"],"route_count":len(routes),"alternatives_note":alternatives_note or count_note,"trip":{"origin":a,"destination":b,"departure":data["departure"].isoformat(),"load_lb":data["load_lb"],"interval_miles":data["interval_miles"]},"safety_note":"Routes use the configured routing profile. Confirm truck dimensions, weight limits, bridge clearances, road restrictions, and official advisories; weather thresholds are assessment guidance, not safety certification."})
