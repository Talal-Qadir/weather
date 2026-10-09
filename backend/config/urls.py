from django.urls import path
from routing.views import health, config_status, geocode, analyze
urlpatterns = [path("api/health/", health), path("api/config/status/", config_status), path("api/geocode/", geocode), path("api/routes/analyze/", analyze)]
