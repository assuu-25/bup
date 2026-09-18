from __future__ import annotations

import requests
import streamlit as st


def build_request_payload(
    scenario_id: str,
    operator_notes: list[str],
    battery_capacity_kwh: float,
    hours: list[dict] | None = None,
) -> dict:
    """Create a valid API request payload for the FastAPI backend."""
    if hours is None:
        hours = [
            {
                "hour": hour,
                "demand_kwh": 40.0 + (hour % 12) * 2.0,
                "solar_kwh": max(0.0, 9.0 - abs(hour - 13) * 1.5),
                "tariff_bdt_per_kwh": 7.0 + (hour // 6) * 2.0 + (hour % 6) * 0.25,
            }
            for hour in range(24)
        ]

    battery_capacity = float(battery_capacity_kwh)
    battery = {
        "capacity_kwh": battery_capacity,
        "initial_energy_kwh": min(battery_capacity, battery_capacity * 0.5),
        "minimum_energy_kwh": 0.0,
        "max_charge_kwh_per_hour": battery_capacity,
        "max_discharge_kwh_per_hour": battery_capacity,
    }
    return {
        "scenario_id": scenario_id,
        "operator_notes": list(operator_notes),
        "battery": battery,
        "hours": hours,
    }


def render_app() -> None:
    st.set_page_config(page_title="GridWise", page_icon="⚡", layout="wide")
    st.title("⚡ GridWise")
    st.subheader("Smart Campus 24-Hour Energy Planning")

    notes = st.text_area(
        "Enter campus operation notes",
        height=200,
        placeholder="Example: Tomorrow is a working day. Keep the library open...",
    )
    battery_capacity = st.number_input(
        "Battery capacity (kWh)",
        min_value=1.0,
        value=200.0,
        step=10.0,
    )
    api_url = st.text_input("API URL", value="http://localhost:8000/optimize-energy")

    if st.button("Generate 24-Hour Plan"):
        if not notes.strip():
            st.warning("Please enter operation notes.")
            return

        st.info("Processing...")
        payload = build_request_payload(
            scenario_id="streamlit-demo",
            operator_notes=[note.strip() for note in notes.splitlines() if note.strip()],
            battery_capacity_kwh=battery_capacity,
        )

        try:
            response = requests.post(api_url, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            st.success("Plan generated.")
            st.json(result)
        except requests.RequestException as exc:
            st.error(f"Connection failed: {exc}")
            st.code(f"Try running: uvicorn main:app --host 0.0.0.0 --port 8000")


if __name__ == "__main__":
    render_app()