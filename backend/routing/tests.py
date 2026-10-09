from datetime import timedelta
from unittest.mock import Mock, patch
import requests
from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.test import APIClient
from .providers import directions, geocode, sample_line, ProviderError

def encode_test_polyline(points):
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    def unsigned(value):
        result = ""
        while value > 0x1F:
            result += alphabet[(value & 0x1F) | 0x20]
            value >>= 5
        return result + alphabet[value]
    def signed(value):
        return unsigned((~(value << 1)) if value < 0 else value << 1)
    encoded = unsigned(1) + unsigned(5) + unsigned(0) + unsigned(0)
    lat = lon = 0
    for next_lat, next_lon in points:
        next_lat, next_lon = round(next_lat * 100000), round(next_lon * 100000)
        encoded += signed(next_lat - lat) + signed(next_lon - lon)
        lat, lon = next_lat, next_lon
    return encoded

class RouteProviderTests(SimpleTestCase):
    def test_geocoder_parses_pelias_features(self):
        response=Mock(status_code=200); response.json.return_value={"features":[{"geometry":{"coordinates":[-71.06,42.36]},"properties":{"label":"Boston, Massachusetts","locality":"Boston","region":"Massachusetts","country":"United States","postalcode":"02108"}}]}
        geocode.cache_clear()
        with patch("routing.providers.requests.get",return_value=response),patch.dict("os.environ",{"OPENROUTESERVICE_API_KEY":"test","HEIGIT_API_BASE_URL":"https://api.heigit.org"}):
            result=geocode("Boston unique test")
        self.assertEqual(result,[{"label":"Boston, Massachusetts","lat":42.36,"lon":-71.06,"locality":"Boston","region":"Massachusetts","country":"United States","postalcode":"02108"}])
    def test_geocoder_sends_street_and_small_locality_queries_without_rewriting(self):
        response=Mock(status_code=200); response.json.return_value={"features":[{"geometry":{"coordinates":[-0.12,51.51]},"properties":{"label":"17 High Street, Smallford, England","locality":"Smallford","region":"England","country":"United Kingdom"}}]}
        geocode.cache_clear()
        with patch("routing.providers.requests.get",return_value=response) as get,patch.dict("os.environ",{"OPENROUTESERVICE_API_KEY":"test"}):
            result=geocode("17 High Street, Smallford")
        self.assertEqual(get.call_args.kwargs["params"]["text"],"17 High Street, Smallford")
        self.assertEqual(result[0]["label"],"17 High Street, Smallford, England")
        self.assertAlmostEqual(result[0]["lat"],51.51)
    def test_duplicate_provider_geometries_are_rejected(self):
        same={"features":[{"geometry":{"coordinates":[[0,0],[1,1]]},"properties":{"summary":{"distance":1000,"duration":1000}}}]}
        response=Mock(status_code=200); response.json.return_value=same
        with patch("routing.providers.requests.post",return_value=response),patch.dict("os.environ",{"OPENROUTESERVICE_API_KEY":"test"}):
            routes=directions({"lat":0,"lon":0},{"lat":1,"lon":1},timezone.now())
        self.assertEqual(len(routes),1)
        self.assertEqual(routes[0]["_alternatives_note"],"1 distinct route is available for this journey.")
    def test_partial_heigit_failure_falls_back_to_three_distinct_here_routes(self):
        def response(coords,distance=1000):
            item=Mock(status_code=200); item.json.return_value={"features":[{"geometry":{"coordinates":coords},"properties":{"summary":{"distance":distance,"duration":1000+distance}}}]}; return item
        unavailable=Mock(status_code=503); unavailable.json.return_value={"error":{"message":"brief provider outage"}}
        responses=[unavailable,unavailable]
        here=Mock(status_code=200); here.json.return_value={"routes":[{"sections":[{"summary":{"length":1000+i*100,"duration":1000+i*100},"polyline":encode_test_polyline([[0,0],[1+i*.1,1]])}]} for i in range(3)]}
        with patch("routing.providers.requests.post",side_effect=responses),patch("routing.providers.requests.get",return_value=here),patch("routing.providers.time.sleep"),patch.dict("os.environ",{"OPENROUTESERVICE_API_KEY":"test","HERE_ROUTING_API_KEY":"here-test"}):
            routes=directions({"lat":0,"lon":0},{"lat":1,"lon":1},timezone.now())
        self.assertEqual(len(routes),3)
        self.assertEqual(len({tuple(map(tuple,route["geometry"])) for route in routes}),3)
    def test_provider_parses_real_geojson_shape_and_multiple_alternatives(self):
        feature=lambda distance, duration, coords: {"type":"Feature","geometry":{"type":"LineString","coordinates":coords},"properties":{"summary":{"distance":distance,"duration":duration}}}
        response=Mock(status_code=200); response.json.return_value={"features":[feature(1609.344,3600,[[0,0],[1,1]]),feature(3218.688,4200,[[0,0],[2,2]])]}
        with patch("routing.providers.requests.post",return_value=response),patch.dict("os.environ",{"OPENROUTESERVICE_API_KEY":"test"}):
            result=directions({"lat":0,"lon":0},{"lat":1,"lon":1},timezone.now())
        self.assertEqual(len(result),2); self.assertAlmostEqual(result[0]["distance_miles"],1); self.assertEqual(result[1]["geometry"],[[0,0],[2,2]])
    def test_successful_route_uses_heigit_directions_endpoint_and_expected_payload(self):
        def response_for(*args,**kwargs):
            body=kwargs["json"]
            end=1.1 if "alternative_routes" in body else 1.0 if body.get("preference")=="recommended" else 1.2
            response=Mock(status_code=200); response.json.return_value={"features":[{"geometry":{"coordinates":[[0,0],[end,end]]},"properties":{"summary":{"distance":1609.344,"duration":3600+int(end*100)}}}]}
            return response
        origin={"lat":0,"lon":0}; destination={"lat":1,"lon":1}
        with patch("routing.providers.requests.post",side_effect=response_for) as post,patch.dict("os.environ",{"OPENROUTESERVICE_API_KEY":"test-key","HEIGIT_API_BASE_URL":"https://api.heigit.org","OPENROUTESERVICE_PROFILE":"driving-hgv"}):
            routes=directions(origin,destination,timezone.now())
        self.assertEqual(len(routes),3)
        self.assertEqual(post.call_count,3)
        primary_args,primary_kwargs=post.call_args_list[0]
        alternative_args,alternative_kwargs=post.call_args_list[1]
        self.assertEqual(primary_args[0],"https://api.heigit.org/openrouteservice/v2/directions/driving-hgv/geojson")
        self.assertEqual(primary_kwargs["json"]["coordinates"],[[0,0],[1,1]])
        self.assertIn("ferries",primary_kwargs["json"]["options"]["avoid_features"])
        self.assertNotIn("alternative_routes",primary_kwargs["json"])
        self.assertEqual(alternative_args[0],primary_args[0])
        self.assertEqual(alternative_kwargs["json"]["alternative_routes"]["target_count"],3)
        self.assertEqual(post.call_args_list[2].kwargs["json"]["preference"],"fastest")
        self.assertEqual(alternative_kwargs["timeout"],15)
    def test_long_primary_route_attempts_alternative_then_supported_hgv_preferences(self):
        def response_for(*args,**kwargs):
            preference=kwargs["json"].get("preference", "alternative")
            end={"recommended":1.0,"alternative":1.05,"fastest":1.1,"shortest":1.2}[preference]
            response=Mock(status_code=200); response.json.return_value={"features":[{"geometry":{"coordinates":[[0,0],[end,end]]},"properties":{"summary":{"distance":100001+end,"duration":9000+int(end*100)}}}]}
            return response
        with patch("routing.providers.requests.post",side_effect=response_for) as post,patch.dict("os.environ",{"OPENROUTESERVICE_API_KEY":"test-key"}):
            routes=directions({"lat":0,"lon":0},{"lat":1,"lon":1},timezone.now())
        self.assertEqual(len(routes),3)
        self.assertAlmostEqual(routes[0]["distance_miles"],100001/1609.344,places=2)
        self.assertNotIn("_alternatives_note",routes[0])
        self.assertEqual(post.call_count,4)
        self.assertIn("alternative_routes",post.call_args_list[1].kwargs["json"])
        self.assertEqual([call.kwargs["json"].get("preference") for call in post.call_args_list],["recommended","recommended","fastest","shortest"])
    def test_short_primary_route_requests_alternatives_and_keeps_provider_routes(self):
        primary=Mock(status_code=200); primary.json.return_value={"features":[{"geometry":{"coordinates":[[0,0],[.1,.1]]},"properties":{"summary":{"distance":95000,"duration":5000}}}]}
        alternatives=Mock(status_code=200); alternatives.json.return_value={"features":[{"geometry":{"coordinates":[[0,0],[.1,.1]]},"properties":{"summary":{"distance":95000,"duration":5000}}},{"geometry":{"coordinates":[[0,0],[.11,.1]]},"properties":{"summary":{"distance":99000,"duration":5200}}}]}
        fastest=Mock(status_code=200); fastest.json.return_value={"features":[{"geometry":{"coordinates":[[0,0],[.12,.1]]},"properties":{"summary":{"distance":98000,"duration":5100}}}]}
        with patch("routing.providers.requests.post",side_effect=[primary,alternatives,fastest]) as post,patch.dict("os.environ",{"OPENROUTESERVICE_API_KEY":"test-key"}):
            routes=directions({"lat":0,"lon":0},{"lat":.1,"lon":.1},timezone.now())
        self.assertEqual(len(routes),3)
        self.assertEqual(post.call_count,3)
        self.assertIn("alternative_routes",post.call_args_list[1].kwargs["json"])
    def test_provider_503_retries_once_logs_sanitized_details_and_returns_clear_error(self):
        failed=Mock(status_code=503); failed.json.return_value={"error":{"message":"upstream outage test-key"}}
        recovered=Mock(status_code=200); recovered.json.return_value={"features":[{"geometry":{"coordinates":[[0,0],[1,1]]},"properties":{"summary":{"distance":1000,"duration":1000}}}]}
        with patch("routing.providers.requests.post",return_value=failed) as post,patch("routing.providers.time.sleep"),patch.dict("os.environ",{"OPENROUTESERVICE_API_KEY":"test-key"}),self.assertLogs("routing.providers",level="WARNING") as logs:
            with self.assertRaisesRegex(ProviderError,r"temporarily unavailable \(HTTP 503\)"):
                directions({"lat":0,"lon":0},{"lat":1,"lon":1},timezone.now())
        self.assertEqual(post.call_count,2)
        self.assertIn("status=503",logs.output[0])
        self.assertIn("upstream outage [redacted]",logs.output[0])
        self.assertNotIn("test-key", " ".join(logs.output))
    def test_rate_limit_stops_additional_route_strategy_requests(self):
        limited=Mock(status_code=429); limited.json.return_value={"error":{"message":"quota reached"}}
        with patch("routing.providers.requests.post",return_value=limited) as post,patch.dict("os.environ",{"OPENROUTESERVICE_API_KEY":"test-key"}):
            with self.assertRaises(ProviderError) as error:
                directions({"lat":0,"lon":0},{"lat":1,"lon":1},timezone.now())
        self.assertEqual(error.exception.status_code,429)
        self.assertEqual(post.call_count,1)
    def test_transient_503_then_success_returns_real_provider_route(self):
        failed=Mock(status_code=503); failed.json.return_value={"error":{"message":"temporarily unavailable"}}
        recovered=Mock(status_code=200); recovered.json.return_value={"features":[{"geometry":{"coordinates":[[0,0],[1,1]]},"properties":{"summary":{"distance":1000,"duration":1000}}}]}
        calls=[]
        def recover_once(*args,**kwargs):
            calls.append(kwargs)
            return failed if len(calls)==1 else recovered
        with patch("routing.providers.requests.post",side_effect=recover_once),patch("routing.providers.time.sleep"),patch.dict("os.environ",{"OPENROUTESERVICE_API_KEY":"test-key"}):
            routes=directions({"lat":0,"lon":0},{"lat":1,"lon":1},timezone.now())
        self.assertEqual(len(routes),1); self.assertAlmostEqual(routes[0]["distance_miles"],1000/1609.344)
    def test_provider_keeps_single_available_route(self):
        response=Mock(status_code=200); response.json.return_value={"features":[{"geometry":{"coordinates":[[0,0],[1,1]]},"properties":{"summary":{"distance":5000,"duration":1000}}}]}
        with patch("routing.providers.requests.post",return_value=response),patch.dict("os.environ",{"OPENROUTESERVICE_API_KEY":"test"}): self.assertEqual(len(directions({"lat":0,"lon":0},{"lat":1,"lon":1},timezone.now())),1)
    def test_provider_failure_is_actionable(self):
        response=Mock(status_code=500); response.raise_for_status.side_effect=requests.HTTPError("provider failed")
        with patch("routing.providers.requests.post",return_value=response),patch.dict("os.environ",{"OPENROUTESERVICE_API_KEY":"test"}):
            with self.assertRaises(ProviderError): directions({"lat":0,"lon":0},{"lat":1,"lon":1},timezone.now())
    def test_alternative_distance_limit_400_falls_back_to_real_primary_route(self):
        primary=Mock(status_code=200); primary.json.return_value={"features":[{"geometry":{"coordinates":[[0,0],[.1,.1]]},"properties":{"summary":{"distance":90000,"duration":5000}}}]}
        rejected=Mock(status_code=400); rejected.json.return_value={"error":{"message":"The approximated route distance must not be greater than 100000.0 meters for use with the alternative Routes algorithm."}}
        fastest=Mock(status_code=200); fastest.json.return_value={"features":[{"geometry":{"coordinates":[[0,0],[.12,.1]]},"properties":{"summary":{"distance":91000,"duration":5200}}}]}
        shortest=Mock(status_code=200); shortest.json.return_value={"features":[{"geometry":{"coordinates":[[0,0],[.13,.1]]},"properties":{"summary":{"distance":92000,"duration":5300}}}]}
        with patch("routing.providers.requests.post",side_effect=[primary,rejected,fastest,shortest]),patch.dict("os.environ",{"OPENROUTESERVICE_API_KEY":"test-key"}):
            routes=directions({"lat":0,"lon":0},{"lat":.1,"lon":.1},timezone.now())
        self.assertEqual(len(routes),3)
        self.assertAlmostEqual(routes[0]["distance_miles"],90000/1609.344)
        self.assertNotIn("_alternatives_note",routes[0])

    def test_long_distance_limit_uses_here_truck_fallback_with_same_global_coordinates(self):
        rejected=Mock(status_code=400); rejected.json.return_value={"error":{"message":"The approximated route distance is over maximum distance for routing."}}
        here=Mock(status_code=200); here.json.return_value={"routes":[{"sections":[{"summary":{"length":5000000,"duration":80000},"polyline":encode_test_polyline([[31.55,74.34],[35,55],[45,20],[51.5,-.12]])}]}]}
        origin={"lat":31.55,"lon":74.34}; destination={"lat":51.5,"lon":-0.12}
        with patch("routing.providers.requests.post",return_value=rejected),patch("routing.providers.requests.get",return_value=here) as get,patch.dict("os.environ",{"OPENROUTESERVICE_API_KEY":"ors-test","HERE_ROUTING_API_KEY":"here-secret"}):
            routes=directions(origin,destination,timezone.now())
        self.assertEqual(routes[0]["provider"],"here")
        params=get.call_args.kwargs["params"]
        self.assertEqual(params["origin"],"31.55,74.34")
        self.assertEqual(params["destination"],"51.5,-0.12")
        self.assertEqual(params["transportMode"],"truck")
        self.assertEqual(params["avoid[features]"],"ferry")
        self.assertEqual(params["apiKey"],"here-secret")  # Sent only in this server-side provider request.

    def test_here_duplicates_and_ferry_sections_are_not_presented_as_routes(self):
        from .providers import _parse_here_routes
        road={"summary":{"length":1000,"duration":1000},"polyline":encode_test_polyline([[0,0],[1,1]])}
        payload={"routes":[{"sections":[road]},{"sections":[road]},{"sections":[{**road,"transport":{"mode":"ferry"}}]},{"sections":[{**road,"polyline":encode_test_polyline([[0,0],[2,2]])}]}]}
        parsed=_parse_here_routes(payload,"test")
        self.assertEqual(len(parsed),3)
        self.assertEqual(parsed[0]["geometry"],parsed[1]["geometry"])

    def test_disconnected_intercontinental_locations_return_clear_no_road_error(self):
        no_route=Mock(status_code=200); no_route.json.return_value={"routes":[]}
        with patch("routing.providers.requests.get",return_value=no_route),patch.dict("os.environ",{"HERE_ROUTING_API_KEY":"here-test"},clear=True):
            with self.assertRaises(ProviderError) as error:
                directions({"lat":31.55,"lon":74.34},{"lat":40.71,"lon":-74.0},timezone.now())
        self.assertEqual(error.exception.status_code,422)
        self.assertIn("No continuous truck-driving road route",str(error.exception))
        self.assertIn("shipping are outside",str(error.exception))

    def test_here_rate_limit_does_not_retry_or_call_another_strategy(self):
        limited=Mock(status_code=429); limited.json.return_value={"error":{"message":"quota reached"}}
        with patch("routing.providers.requests.get",return_value=limited) as get,patch.dict("os.environ",{"HERE_ROUTING_API_KEY":"here-test"},clear=True):
            with self.assertRaises(ProviderError) as error:
                directions({"lat":1,"lon":1},{"lat":2,"lon":2},timezone.now())
        self.assertEqual(error.exception.status_code,429)
        self.assertEqual(get.call_count,1)
    def test_distance_sampling_uses_cumulative_polyline_length_and_endpoints(self):
        points=sample_line([[0,0],[0,1],[0,2]],60)
        self.assertEqual(points[0],(0,0,0.0)); self.assertGreaterEqual(len(points),3); self.assertAlmostEqual(points[-1][0],0); self.assertEqual(points[-1][1],2); self.assertAlmostEqual(points[-1][2],138.2,delta=1)

class AnalyzeValidationTests(SimpleTestCase):
    def setUp(self): self.client=APIClient()
    def test_missing_and_bad_interval_are_rejected_before_provider_calls(self):
        response=self.client.post("/api/routes/analyze/",{"origin":"A","destination":"B","departure":(timezone.now()+timedelta(days=1)).isoformat(),"load_lb":10,"interval_miles":12},format="json")
        self.assertEqual(response.status_code,400); self.assertEqual(response.data["error"]["code"],"validation_error")
    def test_selected_coordinates_are_used_without_regeocoding_and_keep_trip_labels(self):
        departure=(timezone.now()+timedelta(days=1)).isoformat()
        payload={"origin":"Small village","destination":"Rural landmark","origin_place":{"label":"Small village, Region, Country","lat":12.3,"lon":45.6},"destination_place":{"label":"Rural landmark, Region, Country","lat":12.5,"lon":45.9},"departure":departure,"load_lb":1000,"interval_miles":10}
        routes=[{"id":"route-1","name":"Route 1","geometry":[[12.3,45.6],[12.5,45.9]],"distance_miles":25,"duration_seconds":1800,"provider":"openrouteservice"}]
        with patch("routing.views.lookup_places") as lookup,patch("routing.views.directions",return_value=routes) as route_provider,patch("routing.views.batch_weather",return_value=[{"available":False,"reason":"Outside horizon"}]*2):
            response=self.client.post("/api/routes/analyze/",payload,format="json")
        self.assertEqual(response.status_code,200); lookup.assert_not_called()
        self.assertEqual(route_provider.call_args.args[0],payload["origin_place"])
        self.assertEqual(response.data["trip"]["origin"]["label"],payload["origin_place"]["label"])
    def test_selected_place_coordinates_must_be_valid_and_distinct(self):
        base={"origin":"A","destination":"B","origin_place":{"label":"A","lat":0,"lon":0},"destination_place":{"label":"B","lat":0,"lon":0},"departure":(timezone.now()+timedelta(days=1)).isoformat(),"load_lb":1000,"interval_miles":10}
        response=self.client.post("/api/routes/analyze/",base,format="json")
        self.assertEqual(response.status_code,400)
        base["destination_place"]["lon"]=181
        response=self.client.post("/api/routes/analyze/",base,format="json")
        self.assertEqual(response.status_code,400)
    def test_unmatched_legacy_place_text_returns_actionable_422(self):
        payload={"origin":"Unknown village xyz","destination":"Another place","departure":(timezone.now()+timedelta(days=1)).isoformat(),"load_lb":1000,"interval_miles":10}
        with patch("routing.views.lookup_places",side_effect=[[],[]]):
            response=self.client.post("/api/routes/analyze/",payload,format="json")
        self.assertEqual(response.status_code,422)
        self.assertIn("Choose a valid place",response.data["error"]["message"])
    def test_legacy_resolved_locations_must_be_different_before_routing(self):
        point={"label":"Same place","lat":10.0,"lon":20.0}
        payload={"origin":"Same place","destination":"Same place, alternate spelling","departure":(timezone.now()+timedelta(days=1)).isoformat(),"load_lb":1000,"interval_miles":10}
        with patch("routing.views.lookup_places",side_effect=[[point],[point.copy()]]),patch("routing.views.directions") as route_provider:
            response=self.client.post("/api/routes/analyze/",payload,format="json")
        self.assertEqual(response.status_code,400);route_provider.assert_not_called()
    def test_health_endpoint(self):
        response=self.client.get("/api/health/"); self.assertEqual(response.status_code,200); self.assertEqual(response.data,{"status":"ok"})
    def test_analysis_ranks_real_provider_routes_and_reports_checkpoint_weather(self):
        places={"origin":{"label":"Start","lat":0,"lon":0},"destination":{"label":"End","lat":1,"lon":1}}
        route=lambda name,duration:{"id":name,"name":name,"geometry":[[0,0],[0,.145]],"distance_miles":10,"duration_seconds":duration}
        weather_sets=[[{"available":True,"wind_mph":35,"rain_in_hr":0,"snow_in_hr":0}]*2,[{"available":True,"wind_mph":10,"rain_in_hr":0,"snow_in_hr":0}]*2,[{"available":True,"wind_mph":55,"rain_in_hr":0,"snow_in_hr":0}]*2]
        payload={"origin":"Start","destination":"End","departure":(timezone.now()+timedelta(days=1)).isoformat(),"load_lb":20000,"interval_miles":10}
        with patch("routing.views.lookup_places",side_effect=[[places["origin"]],[places["destination"]]]),patch("routing.views.directions",return_value=[route("r1",5000),route("r2",6000),route("r3",4000)]),patch("routing.views.batch_weather",side_effect=weather_sets) as weather:
            response=self.client.post("/api/routes/analyze/",payload,format="json")
        self.assertEqual(response.status_code,200); self.assertEqual(response.data["route_count"],3)
        self.assertIsNone(response.data["alternatives_note"])
        self.assertEqual(weather.call_count,3)
        self.assertEqual(response.data["recommended_route_id"],"r2"); self.assertTrue(response.data["routes"][0]["recommended"])
        self.assertEqual(response.data["routes"][0]["checkpoints"][0]["risk"]["overall_risk"],"Low")
        no_travel_route=next(route for route in response.data["routes"] if route["id"]=="r3")
        self.assertEqual(no_travel_route["summary"]["overall_risk"],"No Travel")
    def test_analysis_prioritizes_severe_miles_then_high_miles(self):
        route=lambda name:{"id":name,"name":name,"geometry":[[0,0],[0,.145]],"distance_miles":10,"duration_seconds":3600}
        payload={"origin":"Start","destination":"End","departure":(timezone.now()+timedelta(days=1)).isoformat(),"load_lb":10000,"interval_miles":10}
        severe=[{"available":True,"wind_mph":50,"rain_in_hr":0,"snow_in_hr":0}]*2
        high=[{"available":True,"wind_mph":40,"rain_in_hr":0,"snow_in_hr":0}]*2
        with patch("routing.views.lookup_places",side_effect=[[{"label":"Start","lat":0,"lon":0}],[{"label":"End","lat":1,"lon":1}]]),patch("routing.views.directions",return_value=[route("severe"),route("high")]),patch("routing.views.batch_weather",side_effect=[severe,high]):
            response=self.client.post("/api/routes/analyze/",payload,format="json")
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data["recommended_route_id"],"high")
        self.assertEqual(response.data["routes"][0]["summary"]["severe_miles"],0)
    def test_provider_503_keeps_existing_api_error_contract(self):
        payload={"origin":"Start","destination":"End","departure":(timezone.now()+timedelta(days=1)).isoformat(),"load_lb":20000,"interval_miles":10}
        with patch("routing.views.lookup_places",side_effect=[[{"label":"Start","lat":0,"lon":0}],[{"label":"End","lat":1,"lon":1}]]),patch("routing.views.directions",side_effect=ProviderError("Routing provider is temporarily unavailable (HTTP 503). Please try again shortly.")):
            response=self.client.post("/api/routes/analyze/",payload,format="json")
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.data["error"]["code"],"provider_error")
        self.assertIn("HTTP 503",response.data["error"]["message"])
    def test_provider_http_400_is_not_misreported_as_503(self):
        payload={"origin":"Start","destination":"End","departure":(timezone.now()+timedelta(days=1)).isoformat(),"load_lb":20000,"interval_miles":10}
        provider_error=ProviderError("Routing distance exceeds provider limit.",status_code=400)
        with patch("routing.views.lookup_places",side_effect=[[{"label":"Start","lat":0,"lon":0}],[{"label":"End","lat":1,"lon":1}]]),patch("routing.views.directions",side_effect=provider_error):
            response=self.client.post("/api/routes/analyze/",payload,format="json")
        self.assertEqual(response.status_code,400)
        self.assertEqual(response.data["error"]["code"],"provider_error")
