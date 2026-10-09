LEVELS = {"Low": 0, "Moderate": 1, "High": 2, "Severe": 3, "No Travel": 4}
def classify_wind(mph):
    if mph is None: return None
    return "Low" if mph < 25 else "Moderate" if mph < 35 else "High" if mph < 45 else "Severe" if mph < 55 else "No Travel"
def classify_rain(value):
    if value is None: return None
    return "Low" if value < .10 else "Moderate" if value < .25 else "High" if value <= .50 else "Severe" if value <= 1 else "No Travel"
def classify_snow(value):
    if value is None: return None
    return "Low" if value < .5 else "Moderate" if value <= 1 else "High" if value <= 2 else "Severe" if value <= 3 else "No Travel"
def assess(weather, load_lb):
    wind, rain, snow = weather.get("wind_mph"), weather.get("rain_in_hr"), weather.get("snow_in_hr")
    risks = {"wind": classify_wind(wind), "rain": classify_rain(rain), "snow": classify_snow(snow)}
    load_risk = None
    if wind is not None:
        if wind >= 55 or (45 <= wind < 55 and load_lb > 30000): load_risk = "No Travel"
        elif 35 <= wind < 45 and load_lb > 40000: load_risk = "Severe"
    candidates = [v for v in [*risks.values(), load_risk] if v]
    overall = max(candidates, key=lambda v: LEVELS[v]) if candidates else "Unavailable"
    reasons = []
    if risks["wind"]: reasons.append(f"Wind {wind:.1f} mph: {risks['wind'].lower()} risk")
    if risks["rain"]: reasons.append(f"Rain {rain:.3f} in/hr: {risks['rain'].lower()} risk")
    if risks["snow"]: reasons.append(f"Snow {snow:.3f} in/hr: {risks['snow'].lower()} risk")
    if load_risk: reasons.append(f"Load rule for {load_lb:,.0f} lb: {load_risk.lower()}")
    if not reasons: reasons.append("Forecast data is unavailable for this checkpoint.")
    return {"wind_risk": risks["wind"], "rain_risk": risks["rain"], "snow_risk": risks["snow"], "load_risk": load_risk, "overall_risk": overall, "no_travel": overall == "No Travel", "explanation": ". ".join(reasons)}
