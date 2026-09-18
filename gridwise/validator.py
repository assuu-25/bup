from math import isfinite


DIRECTIVE_TYPES = {
	"solar_reduction",
	"minimum_battery_reserve",
	"no_charge_window",
	"no_discharge_window",
	"max_grid_window",
	"no_op",
}

WINDOW_TYPES = {
	"minimum_battery_reserve",
	"no_charge_window",
	"no_discharge_window",
	"max_grid_window",
}

REQUIRED_FIELDS = {
	"solar_reduction": {"hours", "factor"},
	"minimum_battery_reserve": {"hours", "minimum_energy_kwh"},
	"no_charge_window": {"hours"},
	"no_discharge_window": {"hours"},
	"max_grid_window": {"hours", "max_grid_kwh"},
	"no_op": set(),
}

ALLOWED_FIELDS = {directive_type: fields | {"type"} for directive_type, fields in REQUIRED_FIELDS.items()}


def _validate_hours(directive, index, allowed_hours, errors):
	if "hours" not in directive:
		errors.append(f"directive {index} must include hours")
		return

	directive_hours = directive["hours"]
	if not isinstance(directive_hours, (list, tuple)):
		errors.append(f"directive {index} hours must be a list")
		return

	if any(not isinstance(hour, int) or isinstance(hour, bool) for hour in directive_hours):
		errors.append(f"directive {index} hours must be integers")
		return

	if len(set(directive_hours)) != len(directive_hours):
		errors.append(f"directive {index} hours must be unique")
	if list(directive_hours) != sorted(directive_hours):
		errors.append(f"directive {index} hours must be sorted ascending")
	if any(hour < 0 or hour > 23 or hour not in allowed_hours for hour in directive_hours):
		errors.append(f"directive {index} hours must be between 0 and 23")


def validate_directives(directives, hours=range(24), battery_capacity=None):
	allowed_hours = set(hours)
	errors = []

	for index, directive in enumerate(directives):
		if not isinstance(directive, dict):
			errors.append(f"directive {index} must be a dictionary")
			continue

		directive_type = directive.get("type")
		if directive_type not in DIRECTIVE_TYPES:
			errors.append(f"directive {index} has an invalid type")
			continue

		missing_fields = REQUIRED_FIELDS[directive_type] - directive.keys()
		if missing_fields:
			errors.append(f"directive {index} is missing: {sorted(missing_fields)}")
		extra_fields = set(directive) - ALLOWED_FIELDS[directive_type]
		if extra_fields:
			errors.append(f"directive {index} has unsupported fields: {sorted(extra_fields)}")

		if directive_type in WINDOW_TYPES or "hours" in directive:
			_validate_hours(directive, index, allowed_hours, errors)

		if directive_type == "solar_reduction":
			factor = directive.get("factor")
			if not isinstance(factor, (int, float)) or isinstance(factor, bool) or not isfinite(factor) or not 0 <= factor <= 1:
				errors.append(f"directive {index} factor must be between 0 and 1")

		if directive_type == "minimum_battery_reserve":
			minimum_energy = directive.get("minimum_energy_kwh")
			if not isinstance(minimum_energy, (int, float)) or isinstance(minimum_energy, bool) or not isfinite(minimum_energy) or minimum_energy < 0:
				errors.append(f"directive {index} minimum_energy_kwh must be finite and non-negative")
			elif battery_capacity is not None and minimum_energy > battery_capacity:
				errors.append(f"directive {index} minimum_energy_kwh must not exceed battery capacity")

		if directive_type == "max_grid_window":
			max_grid = directive.get("max_grid_kwh")
			if not isinstance(max_grid, (int, float)) or isinstance(max_grid, bool) or not isfinite(max_grid) or max_grid < 0:
				errors.append(f"directive {index} max_grid_kwh must be finite and non-negative")

		if directive_type == "no_op":
			if set(directive) - {"type"}:
				errors.append(f"directive {index} no_op must not contain an optimization adjustment")

	return {"valid": not errors, "errors": errors}


def validate_plan(plan, hours, battery, directives, tolerance=0.01):
	errors = []
	if len(plan) != 24 or [item.get("hour") for item in plan] != list(range(24)):
		return {"valid": False, "errors": ["hourly_plan must contain hours 0 through 23 in order"]}

	minimum_energy = battery.minimum_energy_kwh
	capacity = battery.capacity_kwh
	initial_energy = battery.initial_energy_kwh
	previous_energy = initial_energy
	base_solar = {item.hour: item.solar_kwh for item in hours}
	tariffs = {item.hour: item.tariff_bdt_per_kwh for item in hours}
	demand = {item.hour: item.demand_kwh for item in hours}
	solar_factors = {}
	reserve = {}
	no_charge = set()
	no_discharge = set()
	grid_limits = {}
	for directive in directives:
		kind = directive["type"]
		for hour in directive.get("hours", []):
			if kind == "solar_reduction":
				solar_factors[hour] = min(solar_factors.get(hour, 1.0), directive["factor"])
			elif kind == "minimum_battery_reserve":
				reserve[hour] = max(reserve.get(hour, minimum_energy), directive["minimum_energy_kwh"])
			elif kind == "no_charge_window":
				no_charge.add(hour)
			elif kind == "no_discharge_window":
				no_discharge.add(hour)
			elif kind == "max_grid_window":
				grid_limits[hour] = min(grid_limits.get(hour, float("inf")), directive["max_grid_kwh"])

	for item in plan:
		hour = item["hour"]
		grid = item["grid_kwh"]
		solar_used = item["solar_used_kwh"]
		action = item["battery_action"]
		battery_kwh = item["battery_kwh"]
		energy = item["battery_energy_after_kwh"]
		charge = battery_kwh if action == "charge" else 0
		discharge = battery_kwh if action == "discharge" else 0
		if grid < -tolerance or solar_used < -tolerance or battery_kwh < -tolerance:
			errors.append(f"hour {hour} contains a negative value")
		if action not in {"charge", "discharge", "idle"}:
			errors.append(f"hour {hour} has an invalid battery action")
		if action == "idle" and abs(battery_kwh) > tolerance:
			errors.append(f"hour {hour} idle action must have zero battery_kwh")
		if solar_used > base_solar[hour] * solar_factors.get(hour, 1.0) + tolerance:
			errors.append(f"hour {hour} exceeds effective solar")
		if abs(grid + solar_used + discharge - demand[hour] - charge) > tolerance:
			errors.append(f"hour {hour} violates energy balance")
		if energy < minimum_energy - tolerance or energy > capacity + tolerance:
			errors.append(f"hour {hour} violates battery bounds")
		if energy < reserve.get(hour, minimum_energy) - tolerance:
			errors.append(f"hour {hour} violates directive reserve")
		if charge > battery.max_charge_kwh_per_hour + tolerance or discharge > battery.max_discharge_kwh_per_hour + tolerance:
			errors.append(f"hour {hour} violates battery rate limits")
		if hour in no_charge and charge > tolerance:
			errors.append(f"hour {hour} violates no-charge window")
		if hour in no_discharge and discharge > tolerance:
			errors.append(f"hour {hour} violates no-discharge window")
		if hour in grid_limits and grid > grid_limits[hour] + tolerance:
			errors.append(f"hour {hour} violates grid limit")
		expected_energy = previous_energy + charge - discharge
		if abs(energy - expected_energy) > tolerance:
			errors.append(f"hour {hour} violates battery transition")
		previous_energy = energy

	if abs(previous_energy - initial_energy) > tolerance:
		errors.append("final battery energy does not match initial energy")
	return {"valid": not errors, "errors": errors}
