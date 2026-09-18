from pulp import LpBinary, LpMinimize, LpProblem, LpStatus, LpVariable, PULP_CBC_CMD, lpSum


def _value(item, name):
	if isinstance(item, dict):
		return item[name]
	return getattr(item, name)


def _hours_for(directive):
	return directive.get("hours", range(24))


def optimize_energy(hours, battery, directives):
	if len(hours) != 24:
		raise ValueError("exactly 24 hourly inputs are required")

	hour_inputs = sorted(hours, key=lambda item: _value(item, "hour"))
	if [
		_value(hour_input, "hour") for hour_input in hour_inputs
	] != list(range(24)):
		raise ValueError("hourly inputs must contain each hour from 0 through 23")

	capacity = _value(battery, "capacity_kwh")
	initial_energy = _value(battery, "initial_energy_kwh")
	minimum_energy = _value(battery, "minimum_energy_kwh")
	max_charge = _value(battery, "max_charge_kwh_per_hour")
	max_discharge = _value(battery, "max_discharge_kwh_per_hour")

	problem = LpProblem("GridWiseEnergyOptimization", LpMinimize)
	grid = LpVariable.dicts("grid_kwh", range(24), lowBound=0)
	solar_used = LpVariable.dicts("solar_used_kwh", range(24), lowBound=0)
	charge = LpVariable.dicts("charge_kwh", range(24), lowBound=0, upBound=max_charge)
	discharge = LpVariable.dicts("discharge_kwh", range(24), lowBound=0, upBound=max_discharge)
	charging = LpVariable.dicts("charging", range(24), cat=LpBinary)
	battery_energy = LpVariable.dicts(
		"battery_energy_kwh",
		range(24),
		lowBound=minimum_energy,
		upBound=capacity,
	)

	effective_solar = []
	minimum_reserve = [minimum_energy] * 24
	max_grid = [None] * 24
	no_charge_hours = set()
	no_discharge_hours = set()

	for hour in range(24):
		factor = 1.0
		for directive in directives:
			if hour not in _hours_for(directive):
				continue
			directive_type = directive["type"]
			if directive_type == "solar_reduction":
				factor = min(factor, directive["factor"])
			elif directive_type == "minimum_battery_reserve":
				minimum_reserve[hour] = max(minimum_reserve[hour], directive["minimum_energy_kwh"])
			elif directive_type == "max_grid_window":
				limit = directive["max_grid_kwh"]
				max_grid[hour] = limit if max_grid[hour] is None else min(max_grid[hour], limit)
			elif directive_type == "no_charge_window":
				no_charge_hours.add(hour)
			elif directive_type == "no_discharge_window":
				no_discharge_hours.add(hour)
		effective_solar.append(_value(hour_inputs[hour], "solar_kwh") * factor)

	for hour in range(24):
		demand = _value(hour_inputs[hour], "demand_kwh")
		problem += grid[hour] + solar_used[hour] + discharge[hour] == demand + charge[hour]
		problem += solar_used[hour] <= effective_solar[hour]
		problem += charge[hour] <= max_charge * charging[hour]
		problem += discharge[hour] <= max_discharge * (1 - charging[hour])
		problem += battery_energy[hour] == (
			(initial_energy if hour == 0 else battery_energy[hour - 1])
			+ charge[hour]
			- discharge[hour]
		)
		problem += battery_energy[hour] >= minimum_reserve[hour]
		if hour in no_charge_hours:
			problem += charge[hour] == 0
		if hour in no_discharge_hours:
			problem += discharge[hour] == 0
		if max_grid[hour] is not None:
			problem += grid[hour] <= max_grid[hour]

	problem += battery_energy[23] == initial_energy
	problem += lpSum(
		grid[hour] * _value(hour_inputs[hour], "tariff_bdt_per_kwh") for hour in range(24)
	)

	status = problem.solve(PULP_CBC_CMD(msg=False))
	if LpStatus[status] != "Optimal":
		raise ValueError(f"energy optimization is not feasible: {LpStatus[status]}")

	hourly_plan = []
	for hour in range(24):
		charge_value = charge[hour].value() or 0
		discharge_value = discharge[hour].value() or 0
		if charge_value > 1e-7:
			battery_action = "charge"
			battery_value = charge_value
		elif discharge_value > 1e-7:
			battery_action = "discharge"
			battery_value = discharge_value
		else:
			battery_action = "idle"
			battery_value = 0.0
		hourly_plan.append(
			{
				"hour": hour,
				"grid_kwh": grid[hour].value(),
				"solar_used_kwh": solar_used[hour].value(),
				"battery_action": battery_action,
				"battery_kwh": battery_value,
				"battery_energy_after_kwh": battery_energy[hour].value(),
			}
		)

	total_grid = sum(plan["grid_kwh"] for plan in hourly_plan)
	return {
		"hourly_plan": hourly_plan,
		"total_grid_kwh": total_grid,
		"total_cost_bdt": sum(
			plan["grid_kwh"] * _value(hour_inputs[plan["hour"]], "tariff_bdt_per_kwh")
			for plan in hourly_plan
		),
		"peak_grid_kwh": max(plan["grid_kwh"] for plan in hourly_plan),
	}
