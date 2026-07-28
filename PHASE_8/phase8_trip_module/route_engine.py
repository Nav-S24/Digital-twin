"""
route_engine.py
Phase 8 - Trip Intelligence Module

Route Engine
------------
CHANGE LOG (this revision):
  - Routing now PREFERS the OpenRouteService (ORS) API (both geocoding via
    ORS Pelias and directions via ORS Directions) when settings.ors_api_key
    is configured. This replaces the previous "OSM-only" implementation.
  - The public OSRM demo server (OpenStreetMap data) is kept as the
    ALTERNATIVE / fallback routing provider if ORS is unavailable or fails,
    per the requirement "Preferred: ORS, Alternative: OSRM".
  - A deterministic mock generator remains the final fallback so the module
    always produces a result offline.
  - NEW: get_alternate_route() — returns a second route option (via ORS's
    native alternative-routes support when available, otherwise a
    synthesized deterministic alternate) for use when severe weather or
    high trip risk is detected.

Public interface `get_route(...)` is UNCHANGED (same signature, same return
dict shape) so trip_engine.py and all other callers keep working exactly
as before.
"""

from __future__ import annotations

import hashlib
import random
from typing import List, Optional, Tuple

import requests

from config import settings
from utils import get_logger, haversine_km

logger = get_logger(__name__)


class RouteEngine:
    def __init__(self):
        self.mock_mode = settings.force_mock_route
        self.ors_enabled = bool(settings.ors_api_key) and not self.mock_mode

    # ------------------------------------------------------------------ #
    # Public API (UNCHANGED signature/return shape)
    # ------------------------------------------------------------------ #
    def get_route(
        self,
        source: str,
        destination: str,
        source_coords: Optional[List[float]] = None,
        destination_coords: Optional[List[float]] = None,
    ) -> dict:
        """
        Returns a dict with distance_km, duration_min, elevation_gain_m,
        traffic_level, coordinates, source_mode.

        Provider priority: OpenRouteService (preferred) -> OSRM (alternative)
        -> deterministic mock (offline fallback).
        """
        try:
            if self.mock_mode:
                return self._mock_route(source, destination)

            src = source_coords or self._geocode(source)
            dst = destination_coords or self._geocode(destination)

            if not src or not dst:
                logger.warning("Geocoding failed for '%s' -> '%s'; using mock route.", source, destination)
                return self._mock_route(source, destination)

            # --- Preferred: OpenRouteService ---
            if self.ors_enabled:
                route = self._ors_route(src, dst)
                if route is not None:
                    return route
                logger.warning("ORS routing unavailable; falling back to OSRM.")

            # --- Alternative: OSRM (OpenStreetMap data, no key required) ---
            route = self._osrm_route(src, dst)
            if route is None:
                logger.warning("OSRM route lookup failed; using mock route.")
                return self._mock_route(source, destination)

            return route

        except Exception as exc:  # noqa: BLE001
            logger.exception("Route engine failure, falling back to mock: %s", exc)
            return self._mock_route(source, destination)

    def get_alternate_route(
        self,
        source: str,
        destination: str,
        source_coords: Optional[List[float]] = None,
        destination_coords: Optional[List[float]] = None,
    ) -> Optional[dict]:
        """
        NEW: Returns a second, distinct route option for the same
        source/destination pair, used when severe weather or high trip risk
        warrants suggesting an alternative. Returns None if no alternate is
        available and mock synthesis is not desired to be silently faked as
        "live" (mock synthesis is always available, so this effectively
        always returns a route in this implementation, keeping the module
        fully functional offline).
        """
        try:
            if self.mock_mode:
                return self._mock_alternate_route(source, destination)

            src = source_coords or self._geocode(source)
            dst = destination_coords or self._geocode(destination)

            if not src or not dst:
                return self._mock_alternate_route(source, destination)

            if self.ors_enabled:
                alt = self._ors_route(src, dst, alternative_index=1)
                if alt is not None:
                    alt["is_alternate"] = True
                    return alt

            # No native alternate available from OSRM demo server /
            # ORS unavailable -> synthesize a deterministic alternate.
            return self._mock_alternate_route(source, destination)

        except Exception as exc:  # noqa: BLE001
            logger.exception("Alternate route lookup failed, using mock: %s", exc)
            return self._mock_alternate_route(source, destination)

    # ------------------------------------------------------------------ #
    # Live data helpers — geocoding
    # ------------------------------------------------------------------ #
    def _geocode(self, place: str) -> Optional[Tuple[float, float]]:
        """Geocode a place name to (lat, lon). Prefers ORS (Pelias) geocoding
        when an ORS API key is configured; falls back to OSM Nominatim."""
        if self.ors_enabled:
            coords = self._ors_geocode(place)
            if coords is not None:
                return coords
        return self._nominatim_geocode(place)

    def _ors_geocode(self, place: str) -> Optional[Tuple[float, float]]:
        try:
            resp = requests.get(
                f"{settings.ors_base_url.rsplit('/v2', 1)[0]}/geocode/search",
                params={"api_key": settings.ors_api_key, "text": place, "size": 1},
                timeout=6,
            )
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", [])
            if not features:
                return None
            lon, lat = features[0]["geometry"]["coordinates"][:2]
            return float(lat), float(lon)
        except Exception as exc:  # noqa: BLE001
            logger.info("ORS geocoding unavailable (%s); trying Nominatim.", exc)
            return None

    def _nominatim_geocode(self, place: str) -> Optional[Tuple[float, float]]:
        try:
            resp = requests.get(
                f"{settings.nominatim_base_url}/search",
                params={"q": place, "format": "json", "limit": 1},
                headers={"User-Agent": "phase8-trip-intelligence/1.0"},
                timeout=6,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data:
                return None
            return float(data[0]["lat"]), float(data[0]["lon"])
        except Exception as exc:  # noqa: BLE001
            logger.info("Nominatim geocoding unavailable (%s); will use mock fallback.", exc)
            return None

    # ------------------------------------------------------------------ #
    # Live data helpers — routing
    # ------------------------------------------------------------------ #
    def _ors_route(
        self, src: Tuple[float, float], dst: Tuple[float, float], alternative_index: int = 0
    ) -> Optional[dict]:
        """Query the OpenRouteService Directions API (driving-car profile)."""
        try:
            url = f"{settings.ors_base_url}/directions/driving-car/geojson"
            body = {
                "coordinates": [[src[1], src[0]], [dst[1], dst[0]]],  # lon,lat order
                "elevation": True,
                "alternative_routes": {"target_count": 2, "share_factor": 0.6, "weight_factor": 1.4}
                if alternative_index > 0 else None,
            }
            body = {k: v for k, v in body.items() if v is not None}
            headers = {
                "Authorization": settings.ors_api_key,
                "Content-Type": "application/json",
            }
            resp = requests.post(url, json=body, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", [])
            if not features:
                return None

            idx = min(alternative_index, len(features) - 1)
            feature = features[idx]
            props = feature["properties"]
            summary = props.get("summary", {})
            coords = feature["geometry"]["coordinates"]  # [lon, lat, (elev)]
            coords_latlon = [[c[1], c[0]] for c in coords]

            ascent = props.get("ascent")

            return {
                "distance_km": round(summary.get("distance", 0) / 1000.0, 1),
                "duration_min": round(summary.get("duration", 0) / 60.0, 1),
                "elevation_gain_m": round(ascent, 1) if ascent is not None else None,
                "traffic_level": "unknown (ORS free tier has no live traffic layer)",
                "coordinates": coords_latlon,
                "source_mode": "live",
            }
        except Exception as exc:  # noqa: BLE001
            logger.info("ORS routing unavailable (%s).", exc)
            return None

    def _osrm_route(self, src: Tuple[float, float], dst: Tuple[float, float]) -> Optional[dict]:
        """Query the public OSRM demo server for a driving route (alternative provider)."""
        try:
            coord_str = f"{src[1]},{src[0]};{dst[1]},{dst[0]}"  # lon,lat order
            url = f"{settings.osrm_public_base_url}/route/v1/driving/{coord_str}"
            resp = requests.get(
                url,
                params={"overview": "full", "geometries": "geojson"},
                timeout=8,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != "Ok" or not data.get("routes"):
                return None

            leg = data["routes"][0]
            coords = leg["geometry"]["coordinates"]  # [lon, lat] pairs
            coords_latlon = [[c[1], c[0]] for c in coords]

            return {
                "distance_km": round(leg["distance"] / 1000.0, 1),
                "duration_min": round(leg["duration"] / 60.0, 1),
                "elevation_gain_m": None,  # OSRM demo server doesn't provide elevation
                "traffic_level": "unknown (OSM has no live traffic layer)",
                "coordinates": coords_latlon,
                "source_mode": "live",
            }
        except Exception as exc:  # noqa: BLE001
            logger.info("OSRM routing unavailable (%s).", exc)
            return None

    # ------------------------------------------------------------------ #
    # Mock fallback (deterministic per source/destination pair)
    # ------------------------------------------------------------------ #
    def _mock_route(self, source: str, destination: str) -> dict:
        seed = int(hashlib.sha256(f"{source}->{destination}".encode()).hexdigest(), 16) % (10**6)
        rng = random.Random(seed)

        distance_km = round(rng.uniform(50, 900), 1)
        avg_speed_kmph = rng.uniform(45, 70)
        duration_min = round((distance_km / avg_speed_kmph) * 60, 1)
        elevation_gain_m = round(rng.uniform(20, 600), 1)
        traffic_level = rng.choice(["Light", "Moderate", "Heavy"])

        return {
            "distance_km": distance_km,
            "duration_min": duration_min,
            "elevation_gain_m": elevation_gain_m,
            "traffic_level": traffic_level,
            "coordinates": None,
            "source_mode": "mock",
            "is_alternate": False,
        }

    def _mock_alternate_route(self, source: str, destination: str) -> dict:
        """Deterministic alternate: same seed family, offset so it differs
        consistently from the primary mock route but is reproducible."""
        seed = int(hashlib.sha256(f"alt::{source}->{destination}".encode()).hexdigest(), 16) % (10**6)
        rng = random.Random(seed)

        base = self._mock_route(source, destination)
        # A realistic alternate: slightly longer distance, but often less
        # congested (used as the "avoids risk" narrative in the dashboard).
        distance_km = round(base["distance_km"] * rng.uniform(1.05, 1.25), 1)
        avg_speed_kmph = rng.uniform(50, 75)
        duration_min = round((distance_km / avg_speed_kmph) * 60, 1)

        return {
            "distance_km": distance_km,
            "duration_min": duration_min,
            "elevation_gain_m": round(rng.uniform(20, 600), 1),
            "traffic_level": rng.choice(["Light", "Moderate"]),
            "coordinates": None,
            "source_mode": "mock",
            "is_alternate": True,
        }
