import json
import os
import re
from functools import lru_cache
from urllib.error import URLError
from urllib.request import Request, urlopen

from directives import interpret_notes as deterministic_interpret_notes
from validator import validate_directives


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
try:
	OLLAMA_TIMEOUT_SECONDS = max(1.0, float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "5")))
except ValueError:
	OLLAMA_TIMEOUT_SECONDS = 5.0


SYSTEM_PROMPT = """You interpret energy operator notes into JSON directives.
Return only a JSON array with exactly one object per note, in note order.
Each object must use this internal shape:
- solar_reduction: {type, hours, factor}
- minimum_battery_reserve: {type, hours, minimum_energy_kwh}
- no_charge_window: {type, hours}
- no_discharge_window: {type, hours}
- max_grid_window: {type, hours, max_grid_kwh}
- no_op: {type} only
Hours are unique integers, start-inclusive and end-exclusive, from 0 through 23.
For solar reduction, factor is the usable fraction remaining.
Use no_op for notes unrelated to today's energy schedule.
Do not invent demand, solar, tariff, or battery values.
"""


def _extract_json(text):
	text = text.strip()
	if text.startswith("```"):
		text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
	return json.loads(text)


def _ask_ollama(notes, battery_capacity):
	payload = {
		"model": OLLAMA_MODEL,
		"system": SYSTEM_PROMPT,
		"prompt": json.dumps({"operator_notes": notes, "battery_capacity_kwh": battery_capacity}),
		"stream": False,
		"format": "json",
	}
	request = Request(
		f"{OLLAMA_URL.rstrip('/')}/api/generate",
		data=json.dumps(payload).encode("utf-8"),
		headers={"Content-Type": "application/json"},
		method="POST",
	)
	with urlopen(request, timeout=OLLAMA_TIMEOUT_SECONDS) as response:
		body = json.loads(response.read().decode("utf-8"))
	return _extract_json(body["response"])


@lru_cache(maxsize=256)
def _ask_ollama_cached(notes, battery_capacity):
	return _ask_ollama(list(notes), battery_capacity)


def interpret_notes(operator_notes, battery_capacity):
	deterministic_directives = deterministic_interpret_notes(operator_notes, battery_capacity)
	try:
		directives = [
			directive.copy()
			for directive in _ask_ollama_cached(tuple(operator_notes), battery_capacity)
		]
		if not isinstance(directives, list) or len(directives) != len(operator_notes):
			raise ValueError("Ollama returned the wrong number of directives")
		validation = validate_directives(directives, battery_capacity=battery_capacity)
		if not validation["valid"]:
			raise ValueError("Ollama returned invalid directives")
		for index, directive in enumerate(directives):
			if directive.get("type") == "no_op" and deterministic_directives[index].get("type") != "no_op":
				directives[index] = deterministic_directives[index]
		return directives
	except (OSError, URLError, KeyError, TypeError, ValueError, json.JSONDecodeError):
		return deterministic_directives
