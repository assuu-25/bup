from math import isfinite

from pydantic import BaseModel, Field, field_validator, model_validator


class HourInput(BaseModel):
	hour: int = Field(ge=0, le=23)
	demand_kwh: float = Field(ge=0)
	solar_kwh: float = Field(ge=0)
	tariff_bdt_per_kwh: float = Field(ge=0)

	@field_validator("demand_kwh", "solar_kwh", "tariff_bdt_per_kwh")
	@classmethod
	def finite_value(cls, value):
		if not isfinite(value):
			raise ValueError("value must be finite")
		return value


class BatteryInput(BaseModel):
	capacity_kwh: float = Field(ge=0)
	initial_energy_kwh: float = Field(ge=0)
	minimum_energy_kwh: float = Field(ge=0)
	max_charge_kwh_per_hour: float = Field(ge=0)
	max_discharge_kwh_per_hour: float = Field(ge=0)

	@field_validator(
		"capacity_kwh",
		"initial_energy_kwh",
		"minimum_energy_kwh",
		"max_charge_kwh_per_hour",
		"max_discharge_kwh_per_hour",
	)
	@classmethod
	def finite_value(cls, value):
		if not isfinite(value):
			raise ValueError("value must be finite")
		return value

	@model_validator(mode="after")
	def validate_energy_bounds(self):
		if self.initial_energy_kwh > self.capacity_kwh:
			raise ValueError("initial energy must not exceed battery capacity")
		if self.minimum_energy_kwh > self.capacity_kwh:
			raise ValueError("minimum energy must not exceed battery capacity")
		return self


class OptimizeRequest(BaseModel):
	scenario_id: str
	operator_notes: list[str] = Field(min_length=1, max_length=3)
	hours: list[HourInput] = Field(min_length=24, max_length=24)
	battery: BatteryInput

	@field_validator("operator_notes")
	@classmethod
	def validate_notes(cls, notes):
		if any(not note.strip() for note in notes):
			raise ValueError("operator notes must not be empty")
		return notes

	@model_validator(mode="after")
	def validate_hours(self):
		if sorted(hour.hour for hour in self.hours) != list(range(24)):
			raise ValueError("hours must contain each hour from 0 through 23 exactly once")
		return self
