"""tests/test_preprocessing.py"""

import pandas as pd
import pytest

from preprocessing.data_loader import VEDDataLoader
from utils.exceptions import DataLoadError


class TestVEDDataLoader:
    def setup_method(self):
        self.loader = VEDDataLoader()

    def test_load_csv_missing_file_raises(self):
        with pytest.raises(DataLoadError):
            self.loader.load_csv("/nonexistent/path.csv")

    def test_handle_missing_values_drops_core_nan_rows(self):
        df = pd.DataFrame({
            "veh_id": [1, 1, None], "trip_id": [1, 1, 1],
            "timestamp_ms": [0, 100, 200], "latitude": [42.0, 42.1, 42.2],
            "longitude": [-83.0, -83.1, -83.2], "speed_kmh": [10, 20, 30],
            "day_num": [1, 1, 1],
        })
        cleaned = self.loader.handle_missing_values(df)
        assert len(cleaned) == 2

    def test_remove_duplicates(self):
        df = pd.DataFrame({
            "veh_id": [1, 1, 1], "trip_id": [1, 1, 1],
            "timestamp_ms": [0, 0, 100], "latitude": [42.0, 42.0, 42.1],
            "longitude": [-83.0, -83.0, -83.1], "speed_kmh": [10, 10, 20],
        })
        cleaned = self.loader.remove_duplicates(df)
        assert len(cleaned) == 2

    def test_convert_timestamps_produces_datetime(self):
        df = pd.DataFrame({"day_num": [1.0], "timestamp_ms": [5000]})
        result = self.loader.convert_timestamps(df.copy())
        assert pd.api.types.is_datetime64_any_dtype(result["timestamp"])
        assert result["timestamp"].iloc[0].year == 2017

    def test_clean_gps_drops_out_of_bounds_coordinates(self):
        df = pd.DataFrame({
            "veh_id": [1, 1], "trip_id": [1, 1],
            "timestamp": pd.to_datetime(["2017-11-01 00:00:00", "2017-11-01 00:00:01"]),
            "latitude": [42.28, 200.0], "longitude": [-83.7, -83.7],
            "speed_kmh": [10, 10],
        })
        cleaned = self.loader.clean_gps(df)
        assert len(cleaned) == 1

    def test_segment_trips_drops_short_trips(self):
        df = pd.DataFrame({
            "veh_id": [1] * 15 + [2] * 2,
            "trip_id": [1] * 15 + [2] * 2,
        })
        result = self.loader.segment_trips(df)
        assert result["global_trip_id"].nunique() == 1
        assert (result["veh_id"] == 2).sum() == 0

    def test_run_pipeline_end_to_end(self, tmp_path):
        csv_content = (
            "DayNum,VehId,Trip,Timestamp(ms),Latitude[deg],Longitude[deg],"
            "Vehicle Speed[km/h],MAF[g/sec],Engine RPM[RPM],Absolute Load[%],"
            "OAT[DegC],Fuel Rate[L/hr],Air Conditioning Power[kW],"
            "Air Conditioning Power[Watts],Heater Power[Watts],HV Battery Current[A],"
            "HV Battery SOC[%],HV Battery Voltage[V],Short Term Fuel Trim Bank 1[%],"
            "Short Term Fuel Trim Bank 2[%],Long Term Fuel Trim Bank 1[%],"
            "Long Term Fuel Trim Bank 2[%]\n"
        )
        rows = []
        for i in range(20):
            rows.append(f"1.5,1,1,{i*200},42.28,{-83.70 + i*0.0001},{20+i},10,2000,50,,2,,,,,,,,,,\n")
        csv_content += "".join(rows)
        file_path = tmp_path / "sample.csv"
        file_path.write_text(csv_content)

        result = self.loader.run_pipeline(str(file_path))
        assert not result.empty
        assert "global_trip_id" in result.columns
        assert "timestamp" in result.columns
