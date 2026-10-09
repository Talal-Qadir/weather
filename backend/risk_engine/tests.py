from django.test import SimpleTestCase
from .engine import assess, classify_wind, classify_rain, classify_snow
class RiskThresholdTests(SimpleTestCase):
    def test_wind_boundaries(self):
        self.assertEqual([classify_wind(x) for x in [24.9,25,35,45,55]], ["Low","Moderate","High","Severe","No Travel"])
    def test_precipitation_boundaries(self):
        self.assertEqual([classify_rain(x) for x in [.099,.1,.249,.25,.5,1,1.01]], ["Low","Moderate","Moderate","High","High","Severe","No Travel"])
        self.assertEqual([classify_snow(x) for x in [.49,.5,1,1.01,2,3,3.01]], ["Low","Moderate","Moderate","High","High","Severe","No Travel"])
    def test_load_rules_exact_edges(self):
        self.assertEqual(assess({"wind_mph":45},30000)["overall_risk"],"Severe")
        self.assertEqual(assess({"wind_mph":45},30001)["overall_risk"],"No Travel")
        self.assertEqual(assess({"wind_mph":35},40000)["overall_risk"],"High")
        self.assertEqual(assess({"wind_mph":35},40001)["overall_risk"],"Severe")
        self.assertEqual(assess({"wind_mph":55},1)["overall_risk"],"No Travel")
