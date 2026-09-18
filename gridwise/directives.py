import re


DIRECTIVE_TYPES = {
	"solar_reduction",
	"minimum_battery_reserve",
	"no_charge_window",
	"no_discharge_window",
	"max_grid_window",
	"no_op",
}


NUMBER_WORDS = {
	"zero": 0,
	"one": 1,
	"two": 2,
	"three": 3,
	"four": 4,
	"five": 5,
	"six": 6,
	"seven": 7,
	"eight": 8,
	"nine": 9,
	"ten": 10,
	"eleven": 11,
	"twelve": 12,
}


def _hour(value: str, meridiem: str | None) -> int:
	value = value.lower()
	if value == "noon":
		return 12
	if value == "midnight":
		return 0
	if value in NUMBER_WORDS:
		hour = NUMBER_WORDS[value]
	else:
		hour = int(value.split(":")[0])
	if meridiem:
		hour %= 12
		if meridiem.lower() == "pm":
			hour += 12
	return hour


def _window(note: str) -> list[int] | None:
	time = r"(?:\d{1,2}(?::\d{2})?|" + "|".join(NUMBER_WORDS) + r"|noon|midnight)"
	match = re.search(
		rf"(?:from|between)\s+({time})\s*(AM|PM)?\s+(?:until|and|to)\s+"
		rf"({time})\s*(AM|PM)?",
		note,
		re.IGNORECASE,
	)
	if not match:
		match = re.search(
			rf"\b({time})\s*(AM|PM)?\s*(?:-|–)\s*({time})\s*(AM|PM)?\b",
			note,
			re.IGNORECASE,
		)
	if not match:
		return None

	start_meridiem = match.group(2)
	end_meridiem = match.group(4)
	if start_meridiem is None:
		start_meridiem = end_meridiem
	start = _hour(match.group(1), start_meridiem)
	end = _hour(match.group(3), end_meridiem)
	if end <= start:
		end += 24
	return [hour % 24 for hour in range(start, end)]


def _no_op() -> dict:
	return {"type": "no_op"}


def _interpret_note(note: str, battery_capacity: float) -> dict:
	lower_note = note.lower()
	window = _window(note)

	if "solar" in lower_note or "pv" in lower_note or "photovoltaic" in lower_note:
		usable_match = re.search(r"(?:usable|available).*?(\d+(?:\.\d+)?)\s*%", lower_note)
		reduction_match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*reduction", lower_note)
		remaining_match = re.search(
			r"(?:drop|fall|leave|remain|to)\D{0,30}(\d+(?:\.\d+)?)\s*%",
			lower_note,
		)
		if usable_match:
			return {
				"type": "solar_reduction",
				"hours": window or list(range(24)),
				"factor": float(usable_match.group(1)) / 100,
			}
		if reduction_match:
			return {
				"type": "solar_reduction",
				"hours": window or list(range(24)),
				"factor": round(1 - float(reduction_match.group(1)) / 100, 6),
			}
		if remaining_match or "half" in lower_note or "one-fifth" in lower_note:
			factor = (
				float(remaining_match.group(1)) / 100
				if remaining_match
				else 0.2 if "one-fifth" in lower_note else 0.5
			)
			return {"type": "solar_reduction", "hours": window or list(range(24)), "factor": factor}

	if window and "discharge" in lower_note:
		return {"type": "no_discharge_window", "hours": window}
	if window and ("charger" in lower_note or "charge" in lower_note or "charging" in lower_note) and (
		any(word in lower_note for word in ("unavailable", "disabled", "isolated", "outage"))
		or re.search(r"(?:do not|don't|no)\s+(?:charge|charging)", lower_note)
	):
		return {"type": "no_charge_window", "hours": window}

	if window and "grid" in lower_note:
		grid_match = re.search(
			r"(?:at or below|not exceed|limit\s*(?:is|of)?|cap(?:ped)?\s*(?:at|of)?)\s*"
			r"(\d+(?:\.\d+)?)\s*kwh",
			lower_note,
		)
		if grid_match and window:
			return {"type": "max_grid_window", "hours": window, "max_grid_kwh": float(grid_match.group(1))}

	if window and ("at least" in lower_note or "reserve" in lower_note) and "grid" not in lower_note:
		reserve_match = re.search(r"at least\s+(\d+(?:\.\d+)?)\s*%", lower_note)
		absolute_reserve_match = re.search(
			r"(?:at least|keep).*?(\d+(?:\.\d+)?)\s*kwh.*?(?:in reserve|stored|in the battery|battery)",
			lower_note,
		)
		if absolute_reserve_match and window:
			return {
				"type": "minimum_battery_reserve",
				"hours": window,
				"minimum_energy_kwh": float(absolute_reserve_match.group(1)),
			}
		if reserve_match and window:
			return {
				"type": "minimum_battery_reserve",
				"hours": window,
				"minimum_energy_kwh": battery_capacity * float(reserve_match.group(1)) / 100,
			}

	return _no_op()


def interpret_notes(operator_notes, battery_capacity):
	return [_interpret_note(note, battery_capacity) for note in operator_notes]
