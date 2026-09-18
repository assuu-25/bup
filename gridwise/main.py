from fastapi import FastAPI
from fastapi import HTTPException
from llm_interpreter import interpret_notes
from models import OptimizeRequest
from optimizer import optimize_energy
from validator import validate_directives, validate_plan


app = FastAPI()


@app.get("/health")
def health():
	return {"status": "ok"}


@app.post("/optimize-energy")
def optimize_energy_endpoint(request: OptimizeRequest):
	directives = interpret_notes(request.operator_notes, request.battery.capacity_kwh)
	directive_validation = validate_directives(
		directives,
		battery_capacity=request.battery.capacity_kwh,
	)
	if not directive_validation["valid"]:
		raise HTTPException(status_code=422, detail="invalid directive interpretation")

	try:
		result = optimize_energy(request.hours, request.battery, directives)
	except ValueError as error:
		raise HTTPException(status_code=422, detail=str(error)) from error

	plan_validation = validate_plan(result["hourly_plan"], request.hours, request.battery, directives)
	if not plan_validation["valid"]:
		raise HTTPException(status_code=500, detail="optimizer returned an invalid plan")
	calculated_grid = sum(item["grid_kwh"] for item in result["hourly_plan"])
	tariffs = {hour.hour: hour.tariff_bdt_per_kwh for hour in request.hours}
	calculated_cost = sum(
		item["grid_kwh"] * tariffs[item["hour"]]
		for item in result["hourly_plan"]
	)
	if abs(result["total_grid_kwh"] - calculated_grid) > 0.01 or abs(result["total_cost_bdt"] - calculated_cost) > 0.01:
		raise HTTPException(status_code=500, detail="optimizer totals do not match hourly plan")

	interpretation = []
	for index, (note, directive) in enumerate(zip(request.operator_notes, directives)):
		kind = directive["type"]
		adjustment = None if kind == "no_op" else {key: value for key, value in directive.items() if key != "type"}
		interpretation.append({
			"note_index": index,
			"applies": kind != "no_op",
			"directive_type": kind,
			"structured_adjustment": adjustment,
			"explanation": "This note does not affect today's energy schedule." if kind == "no_op" else f"Applied {kind} to the optimization.",
		})

	return {
		"scenario_id": request.scenario_id,
		"directive_interpretation": interpretation,
		**result,
		"plan_summary": "Applied validated operator directives and minimized grid electricity cost with the battery constraints.",
	}
