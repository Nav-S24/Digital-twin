"""
fuel_engine.py
Phase 8 - Trip Intelligence Module

Fuel Cost Estimator
-------------------
Given distance, mileage, current fuel level and live/mocked fuel price,
computes fuel required, total cost, and whether refueling stops are needed
en route.
"""

from __future__ import annotations

import hashlib
import random
from typing import Optional

import requests

from config import settings
from utils import get_logger

logger = get_logger(__name__)

# Reasonable INR/litre fallback bands used for the mock price generator
_MOCK_PRICE_BANDS = {
    "petrol": (96.0, 110.0),
    "diesel": (88.0, 98.0),
    "cng": (75.0, 90.0),
}


class FuelEngine:
    def __init__(self):
        self.mock_mode = settings.force_mock_fuel or not settings.fuel_price_api_key

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def get_fuel_price(self, fuel_type: str = "petrol", region: str = "IN") -> dict:
        """Returns {price_per_litre, currency, source_mode}."""
        fuel_type = fuel_type.lower()
        try:
            if self.mock_mode:
                return self._mock_price(fuel_type, region)
            data = self._fetch_live(fuel_type, region)
            return data if data else self._mock_price(fuel_type, region)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Fuel price API failure, falling back to mock: %s", exc)
            return self._mock_price(fuel_type, region)

    def estimate(
        self,
        distance_km: float,
        mileage_kmpl: float,
        fuel_level_l: float,
        tank_capacity_l: float,
        fuel_type: str = "petrol",
        region: str = "IN",
    ) -> dict:
        """
        Returns dict: fuel_required_l, fuel_available_l, fuel_sufficient,
        fuel_cost, refueling_stops_needed, price_per_litre, source_mode.
        """
        price_info = self.get_fuel_price(fuel_type, region)
        price_per_litre = price_info["price_per_litre"]

        fuel_required_l = round(distance_km / max(mileage_kmpl, 0.1), 2)
        fuel_cost = round(fuel_required_l * price_per_litre, 2)

        fuel_sufficient = fuel_level_l >= fuel_required_l

        refuel_stops = 0
        if not fuel_sufficient:
            shortfall = fuel_required_l - fuel_level_l
            # Assume each stop tops up to full tank capacity
            usable_per_stop = max(tank_capacity_l, 1.0)
            refuel_stops = max(1, int((shortfall + usable_per_stop - 1) // usable_per_stop))

        return {
            "fuel_required_l": fuel_required_l,
            "fuel_available_l": round(fuel_level_l, 2),
            "fuel_sufficient": fuel_sufficient,
            "fuel_cost": fuel_cost,
            "refueling_stops_needed": refuel_stops,
            "price_per_litre": price_per_litre,
            "source_mode": price_info["source_mode"],
        }

    # ------------------------------------------------------------------ #
    # Live data
    # ------------------------------------------------------------------ #
    def _fetch_live(self, fuel_type: str, region: str) -> Optional[dict]:
        # Placeholder for a real fuel-price API integration (provider-specific).
        # Structured so a real endpoint can be dropped in without touching
        # any other module.
        try:
            resp = requests.get(
                "https://api.example-fuelprices.com/v1/price",
                params={"fuel": fuel_type, "region": region, "apikey": settings.fuel_price_api_key},
                timeout=6,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "price_per_litre": float(data["price"]),
                "currency": data.get("currency", "INR"),
                "source_mode": "live",
            }
        except Exception as exc:  # noqa: BLE001
            logger.info("Fuel price API unavailable (%s).", exc)
            return None

    # ------------------------------------------------------------------ #
    # Mock fallback
    # ------------------------------------------------------------------ #
    def _mock_price(self, fuel_type: str, region: str) -> dict:
        low, high = _MOCK_PRICE_BANDS.get(fuel_type, _MOCK_PRICE_BANDS["petrol"])
        seed = int(hashlib.sha256(f"fuel::{fuel_type}::{region}".encode()).hexdigest(), 16) % (10**6)
        rng = random.Random(seed)
        price = round(rng.uniform(low, high), 2)
        return {"price_per_litre": price, "currency": "INR", "source_mode": "mock"}
