# Weather-Aware Truck Routing

RouteWise compares available driving routes using the expected weather at each route checkpoint when a driver is expected to arrive. It is decision support for planning, not a truck-safety certification system.

## What is implemented

- React, TypeScript, and Vite dashboard with debounced place autocomplete, precise location selection, journey validation, loading/error states, route selection, responsive layouts, map, checkpoint details, and a 0–48 hour trip-relative forecast control.
- Django REST API with provider adapters, request validation, structured errors, CORS configuration, API throttling, and a health/config endpoint.
- Up to three distinct routes requested from HeiGIT openrouteservice and, when configured or needed, HERE Routing v8. The service tries supported HeiGIT alternatives and HGV preferences, then uses genuine HERE truck routes when HeiGIT cannot supply enough distinct options. Only provider-returned distinct routes are shown.
- Cumulative-distance checkpoint sampling from route geometry, with an origin point and route endpoint; checkpoint ETA interpolated from route duration.
- Open-Meteo hourly forecasts batched by date and location and cached in-process. Rain and snow hourly accumulations are documented proxies for the assessment's intensity thresholds.
- Central risk engine, load rules, route-mile aggregation, deterministic recommendation ranking, and unit tests for risk boundaries.
- Interactive Leaflet map with every route, selected-route styling, checkpoint markers and detail popups. The color strip is explicitly a checkpoint-based weather-risk overlay, not a continuous spatial heatmap.

## Architecture

`Frontend/src/services/api.ts` calls Django. `backend/routing` validates requests and orchestrates geocoding, routes, weather, and summaries. Provider-specific HTTP calls live in `routing/providers.py` and `weather/service.py`. `risk_engine/engine.py` is independent of Django views and holds threshold logic.

## Providers and limitations

- **Routing:** HeiGIT-hosted openrouteservice Directions v2 is primary (`driving-hgv` by default). It tries native `alternative_routes.target_count=3`, then real supported `recommended`, `fastest`, and `shortest` HGV requests and tollway avoidance if needed. The requests exclude ferries. The 100 km native-alternative and 6,000 km hosted ORS ceilings are provider limits, not application journey validation; a native alternative error does not prevent other route strategies. Configure optional `HERE_ROUTING_API_KEY` to enable HERE Routing v8 as a secondary truck-specific provider for provider distance failures, outages, or missing route diversity. HERE requests use `transportMode=truck`, `fast` and `short` routing modes, up to two alternatives per request, and `avoid[features]=ferry`; ferry/transit sections are discarded, so no route is drawn across water. Both providers use the selected endpoint coordinates. Provider coverage, account quotas, eligible road networks, truck restrictions, and service limits apply; routes are not truck-legal certifications. If the network is disconnected or no provider can find a continuous road route, the API reports that fact. If fewer than three distinct road paths exist, the actual routes and a neutral count message are returned. See [openrouteservice Directions](https://giscience.github.io/openrouteservice/api-reference/endpoints/directions/), [HGV options](https://giscience.github.io/openrouteservice/api-reference/endpoints/directions/routing-options), [ORS service limits](https://openrouteservice.org/restrictions/), [HERE truck routing](https://docs.here.com/routing/docs/routing-v8-truck-routing), [HERE Routes API](https://docs.here.com/routing/reference/routing-api-v8-calculateroutes), and [HERE avoidance](https://docs.here.com/routing/docs/routing-v8-avoidance).
- **Geocoding:** HeiGIT Pelias search with the same openrouteservice API key. Its search endpoint supports address, street, neighbourhood, locality (including towns/hamlets), venue, and postalcode result layers; this app submits international free-text search and preserves selected labels/coordinates. Coverage and address completeness depend on Pelias datasets and the hosted provider. See [Pelias search layers](https://github.com/pelias/documentation/blob/master/search.md#filter-by-data-type) and [structured geocoding](https://github.com/pelias/documentation/blob/master/structured-geocoding.md). Self-hosted openrouteservice does not automatically include the hosted Pelias service; configure a separate compatible geocoder if you self-host routing.
- **Weather:** Open-Meteo hourly forecast. Hourly rain/snow accumulation is used as the closest available proxy for in/hr; it is not an instantaneous intensity measurement. Provider forecasts have a finite horizon. Checkpoint data is marked unavailable outside its coverage; no values are fabricated. Forecast request quota, model, spatial resolution, attribution, and commercial terms depend on the selected Open-Meteo endpoint/plan.
- **Map:** OpenStreetMap standard raster tiles via Leaflet. Display attribution and observe the [tile usage policy](https://operations.osmfoundation.org/policies/tiles/); use a production tile provider for substantial traffic.

Risk rules use the supplied assessment thresholds. Shared rain/snow boundaries are assigned to the more severe band where ranges overlap (rain 0.25 = High, 0.50 = High; snow 1.0 = Moderate, 2.0 = High). Ranking uses fewest Severe-risk miles, then High-risk miles, the lowest average risk score, and shortest duration. No Travel conditions are still prominently flagged and are not described as safe. Routes use driving-HGV graph profile where enabled, but are not certified truck-legal.

## Requirements

- Python 3.10+ and Node.js 20+.
- An openrouteservice API key for geocoding and primary routing (free/paid quotas and endpoint access are controlled by the provider). A HERE Routing API key is optional but recommended for provider fallback and global long-distance coverage.
- Internet access from the backend for provider requests and from the browser for map tiles.

## Local setup

### backend

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `OPENROUTESERVICE_API_KEY` in `backend/.env`. Set `HERE_ROUTING_API_KEY` to enable the secondary truck router; both keys stay on the server. `HEIGIT_API_BASE_URL` defaults to `https://api.heigit.org`. Change `OPENROUTESERVICE_PROFILE` only to a profile supported by your API key/account. Then run:

```powershell
python manage.py check
python manage.py test
python manage.py runserver
```

### frontend

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

Open the Vite URL shown in the terminal (normally `http://localhost:5173`). `VITE_API_BASE_URL` points at the Django API root (`http://localhost:8000/api`).

## Environment variables

See `backend/.env.example` and `frontend/.env.example`. Never commit `.env` or real credentials. In production set `DJANGO_DEBUG=False`, a strong random `DJANGO_SECRET_KEY` (50+ characters), exact allowed hosts, `FRONTEND_ORIGIN`, HTTPS `CSRF_TRUSTED_ORIGINS`, API credentials, and provider endpoints in the hosting environment. Configure HTTPS at the host/reverse proxy and set `DATABASE_URL` to a managed PostgreSQL URL for hosted production. SQLite is the local default. Collect static files with `python manage.py collectstatic --noinput`.

## API

- `GET /api/health/` → `{"status":"ok"}`
- `GET /api/config/status/` → configured provider names and whether routing credentials exist (never returns secrets)
- `GET /api/geocode/?q=Chicago` → `{ "results": [{"label":"…","lat":41.88,"lon":-87.63}] }`
- `POST /api/routes/analyze/` accepts:

```json
{"origin":"Chicago, IL","destination":"Madison, WI","departure":"2030-06-15T08:00:00-05:00","load_lb":36000,"interval_miles":25}
```

A successful response resembles `{ "route_count": 2, "recommended_route_id": "route-2", "routes": [{"id":"route-2","distance_miles":294.2,"duration_seconds":15300,"arrival":"2030-06-15T17:15:00-05:00","summary":{"checkpoint_count":13,"overall_risk":"Moderate","average_risk_score":1.1},"checkpoints":[{"distance_miles":0,"eta":"2030-06-15T08:00:00-05:00","weather":{"available":true,"wind_mph":18.2},"risk":{"overall_risk":"Low"}}]}], "alternatives_note": "2 distinct routes are available for this journey." }`. With three routes the note is `null`. Full success responses also include the trip and safety note. Each route includes its own provider-returned geometry, miles, duration, arrival, checkpoints, risk-mile summary, and rank. Errors use `{ "error": {"code":"…","message":"…","fields":{}} }`. Date-time inputs must include a UTC offset and be in the future. Distances use miles, load pounds, wind mph, precipitation inches/hour proxy, and timestamps ISO 8601.

## Checks and tests

backend: `python manage.py test`, `python manage.py check`. frontend: `npm test`, `npm run build`. Provider calls are not needed for risk-engine tests. Live trip analysis requires configured provider access and is subject to external quotas.

## Production and publication

### GitHub publication

The workspace is not connected to a GitHub account. To publish it, from the project root:

```powershell
git init -b main
git status --short
git add .
git status --short
git commit -m "Build weather-aware truck routing assessment"
git remote add origin https://github.com/<your-account>/weather-aware-truck-routing.git
git push -u origin main
```

Create an empty GitHub repository with that name first. Confirm `.env`, `node_modules`, `dist`, database files, and secrets are ignored before committing.

### Hosting steps

1. Build the frontend with `npm run build`; deploy `frontend/dist` to a static host and set `VITE_API_BASE_URL` to the hosted Django `/api` URL.
2. Deploy `backend` on a Python/Linux service with `pip install -r requirements.txt`, then run `python manage.py migrate`, `python manage.py collectstatic --noinput`, and `gunicorn config.wsgi:application`.
3. Set a strong secret, `DJANGO_DEBUG=False`, `DJANGO_ALLOWED_HOSTS`, `FRONTEND_ORIGIN`, HTTPS `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL`, `OPENROUTESERVICE_API_KEY`, optional `HERE_ROUTING_API_KEY`, `HEIGIT_API_BASE_URL`, and `OPEN_METEO_BASE_URL` in the host's secret/environment settings.
4. Verify `GET /api/health/`, `GET /api/config/status/`, and a real route analysis before sharing the application URL.

No GitHub repository or hosted application has been created by this workspace.

## Walkthrough script (5–10 minutes)

1. Introduce the React/Vite frontend and Django API/provider/risk-engine split.
2. Enter origin, destination, departure, load, and checkpoint spacing; demonstrate explicit place search and validation.
3. Explain HeiGIT HGV routes and the HERE truck-routing fallback; show the actual route count and any neutral count notice when fewer than three distinct paths are returned.
4. Select routes and show map geometries, checkpoint markers, ETAs, and forecast values.
5. Open a checkpoint and explain wind, rain, snow, load rules, and No Travel warnings.
6. Show route ranking, risk miles, and the 0–48-hour trip-relative checkpoint overlay.
7. Explain forecast horizon/precipitation proxies and truck restriction caveat.
8. Run the documented backend tests and frontend build.

## Assessment checklist

- Journey entry and validation: implemented.
- Up to three distinct routes attempted for short and long journeys using provider-backed HGV requests; returned set may contain fewer when ORS responses converge or fail.
- Route geometry and cumulative-distance checkpoints with ETA forecasts: implemented.
- Exact weather/load rules and recommendation: implemented; boundary unit tests included.
- Interactive route map, checkpoints, risk legend, selection, checkpoint risk overlay, 0–48h slider: implemented.
- Mocked provider parsing, API validation/analysis, risk-threshold boundaries, and React journey/loading/error/route-selection/checkpoint/slider interactions: covered by automated tests. Browser console checks, visual responsive QA, live-provider analysis, hosted deployment, GitHub publication, and Loom recording: not yet completed. External credentials and accounts are needed for live end-to-end analysis and publication.

## Product UX, geocoding, and forecast details

The responsive workspace provides Overview, Plan a route, Weather analysis, and planning settings navigation. It does not claim to save trips or provide accounts. Origin and destination use debounced HeiGIT Pelias autocomplete (minimum three characters), with keyboard selection and available locality, region, country, and postal-code context. The selected provider coordinates are submitted to Django and validated there. Existing API clients may continue sending only the text `origin` and `destination` fields; optional `origin_place` and `destination_place` objects enable coordinate-accurate requests.

The browser's configured timezone is used for departure entry and display; the selected instant is sent as UTC to the API. Weather results remain predictions at route checkpoint ETAs, not current observations. Open-Meteo supplies hourly wind, rain, snow, temperature, and visibility where available. The UI shows the forecast-valid hour and backend retrieval time when supplied. Forecast values outside provider coverage remain unavailable. The existing risk engine is authoritative; the frontend only displays its classifications and miles.

New optional backend variables: `HERE_ROUTING_API_KEY` enables fallback truck routes; `HERE_ROUTING_TIMEOUT_SECONDS` defaults to 20 seconds. The existing `OPENROUTESERVICE_API_KEY`, `HEIGIT_API_BASE_URL`, `OPENROUTESERVICE_PROFILE`, `OPENROUTESERVICE_TIMEOUT_SECONDS`, and `OPEN_METEO_BASE_URL` settings continue to apply. HeiGIT/Pelias is used for geocoding; weather and map tiles also require their respective network services.

To verify, run `python manage.py test` and `python manage.py check` from `backend`; run `npm test` and `npm run build` from `Frontend`. For a live smoke test, select street/locality/postal-code suggestions and try a short route, a cross-border route, and a long road-connected route. Confirm provider-returned routes change the map and each has independent ETAs, forecast availability, and weather-risk miles. Ocean-separated locations should report that continuous truck driving is unavailable. A neutral count notice appears only if fewer than three unique provider routes are available.
