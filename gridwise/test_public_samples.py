import json
import unittest
from pathlib import Path

import app
from directives import interpret_notes
from models import OptimizeRequest
from optimizer import optimize_energy
from validator import validate_directives, validate_plan


ROOT = Path(__file__).parent
SAMPLE_FILE = ROOT / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"
EXPECTED_TYPES = {
	"SAMPLE-01": ["solar_reduction", "no_op"],
	"SAMPLE-02": ["no_charge_window"],
	"SAMPLE-03": ["minimum_battery_reserve"],
	"SAMPLE-04": ["no_discharge_window"],
	"SAMPLE-05": ["max_grid_window"],
	"SAMPLE-06": ["solar_reduction", "no_charge_window", "no_op"],
	"SAMPLE-07": ["minimum_battery_reserve", "max_grid_window"],
	"SAMPLE-08": ["no_charge_window", "no_discharge_window"],
	"SAMPLE-09": ["solar_reduction", "no_op"],
	"SAMPLE-10": ["minimum_battery_reserve", "max_grid_window", "no_op"],
}


class PublicSampleTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		with SAMPLE_FILE.open(encoding="utf-8") as sample_file:
			cls.cases = json.load(sample_file)["cases"]

	def test_public_directives_and_plans(self):
		for case in self.cases:
			with self.subTest(case=case["id"]):
				request = OptimizeRequest.model_validate(case["input"])
				directives = interpret_notes(
					request.operator_notes,
					request.battery.capacity_kwh,
				)
				self.assertEqual(
					[directive["type"] for directive in directives],
					EXPECTED_TYPES[case["id"]],
				)
				self.assertEqual(validate_directives(directives)["valid"], True)
				result = optimize_energy(request.hours, request.battery, directives)
				self.assertEqual(len(result["hourly_plan"]), 24)
				self.assertEqual(
					validate_plan(
						result["hourly_plan"],
						request.hours,
						request.battery,
						directives,
					)["valid"],
					True,
				)

	def test_specification_paraphrases(self):
		cases = [
			("PV production will drop to about 20% between 13:00 and 15:00.", {
				"type": "solar_reduction", "hours": [13, 14], "factor": 0.2,
			}),
			("Panel washing from one until three will leave roughly one-fifth of normal solar output.", {
				"type": "solar_reduction", "hours": [1, 2], "factor": 0.2,
			}),
			("Expect an 80% reduction in rooftop solar during the 1-3 PM maintenance window.", {
				"type": "solar_reduction", "hours": [13, 14], "factor": 0.2,
			}),
			("Do not charge the battery between 2 PM and 4 PM.", {
				"type": "no_charge_window", "hours": [14, 15],
			}),
		]
		for note, expected in cases:
			with self.subTest(note=note):
				self.assertEqual(interpret_notes([note], 500)[0], expected)

	def test_app_build_request_payload(self):
		hours = [
			{"hour": hour, "demand_kwh": 10.0 + hour * 0.5, "solar_kwh": max(0.0, 8.0 - hour * 0.2), "tariff_bdt_per_kwh": 4.0 + hour * 0.1}
			for hour in range(24)
		]
		payload = app.build_request_payload(
			scenario_id="demo",
			operator_notes=["Keep the library open.", "Limit grid use after 18:00."],
			battery_capacity_kwh=200,
			hours=hours,
		)
		self.assertEqual(payload["scenario_id"], "demo")
		self.assertEqual(payload["battery"]["capacity_kwh"], 200)
		self.assertEqual(len(payload["hours"]), 24)
		self.assertEqual(payload["operator_notes"][1], "Limit grid use after 18:00.")

	def test_reserve_cannot_exceed_capacity(self):
		self.assertFalse(
			validate_directives(
				[{"type": "minimum_battery_reserve", "hours": [1], "minimum_energy_kwh": 501}],
				battery_capacity=500,
			)["valid"]
		)


if __name__ == "__main__":
	unittest.main()
