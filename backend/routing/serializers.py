from rest_framework import serializers
from django.utils import timezone
import math

class SelectedPlaceSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=300, trim_whitespace=True)
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)
    def validate_lat(self, value):
        if not math.isfinite(value): raise serializers.ValidationError("Latitude must be a finite number.")
        return value
    def validate_lon(self, value):
        if not math.isfinite(value): raise serializers.ValidationError("Longitude must be a finite number.")
        return value

class AnalyzeSerializer(serializers.Serializer):
    origin = serializers.CharField(max_length=300, trim_whitespace=True)
    destination = serializers.CharField(max_length=300, trim_whitespace=True)
    departure = serializers.DateTimeField()
    load_lb = serializers.FloatField(min_value=0.01, max_value=200000)
    interval_miles = serializers.ChoiceField(choices=[10, 25, 50])
    origin_place = SelectedPlaceSerializer(required=False)
    destination_place = SelectedPlaceSerializer(required=False)
    def validate(self, attrs):
        origin = attrs.get("origin_place")
        destination = attrs.get("destination_place")
        if bool(origin) != bool(destination):
            raise serializers.ValidationError("Select both an origin and destination from the location suggestions.")
        if origin and destination and abs(origin["lat"] - destination["lat"]) < 1e-6 and abs(origin["lon"] - destination["lon"]) < 1e-6:
            raise serializers.ValidationError("Origin and destination must be different locations.")
        return attrs
    def validate_departure(self, value):
        if value < timezone.now(): raise serializers.ValidationError("Departure must be in the future.")
        return value
