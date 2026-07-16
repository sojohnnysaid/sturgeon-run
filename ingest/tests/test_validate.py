"""Unit tests for the pure validators. No network, no DB."""
from datetime import date

from sturgeon_ingest import validate

BBOX = (-74.10, 40.55, -73.60, 42.75)  # min_lon, min_lat, max_lon, max_lat


class TestCoordsValid:
    def test_valid(self):
        assert validate.coords_valid(41.0, -73.9) is True

    def test_none_lat(self):
        assert validate.coords_valid(None, -73.9) is False

    def test_none_lon(self):
        assert validate.coords_valid(41.0, None) is False

    def test_string_numbers_ok(self):
        assert validate.coords_valid("41.0", "-73.9") is True

    def test_out_of_earth_range(self):
        assert validate.coords_valid(999.0, -73.9) is False
        assert validate.coords_valid(41.0, -999.0) is False

    def test_non_numeric(self):
        assert validate.coords_valid("abc", "-73.9") is False


class TestInBbox:
    def test_inside(self):
        assert validate.in_bbox(41.0, -73.9, BBOX) is True

    def test_on_boundary(self):
        assert validate.in_bbox(40.55, -74.10, BBOX) is True
        assert validate.in_bbox(42.75, -73.60, BBOX) is True

    def test_outside_lon(self):
        assert validate.in_bbox(41.0, -80.0, BBOX) is False

    def test_outside_lat(self):
        assert validate.in_bbox(10.0, -73.9, BBOX) is False


class TestBasisExcluded:
    def test_fossil_excluded(self):
        assert validate.basis_excluded("FOSSIL_SPECIMEN") is True

    def test_living_excluded(self):
        assert validate.basis_excluded("LIVING_SPECIMEN") is True

    def test_preserved_kept(self):
        assert validate.basis_excluded("PRESERVED_SPECIMEN") is False

    def test_human_observation_kept(self):
        assert validate.basis_excluded("HUMAN_OBSERVATION") is False

    def test_case_insensitive(self):
        assert validate.basis_excluded("fossil_specimen") is True

    def test_none_kept(self):
        assert validate.basis_excluded(None) is False


class TestParseEventDate:
    def test_iso_date(self):
        assert validate.parse_event_date("1999-05-01") == date(1999, 5, 1)

    def test_datetime(self):
        assert validate.parse_event_date("1999-05-01T12:30:00") == date(1999, 5, 1)

    def test_datetime_with_z(self):
        assert validate.parse_event_date("1999-05-01T12:30:00Z") == date(1999, 5, 1)

    def test_datetime_with_offset(self):
        assert validate.parse_event_date("1999-05-01T12:30:00+00:00") == date(1999, 5, 1)

    def test_interval_takes_start(self):
        assert validate.parse_event_date("1999-01-01/1999-12-31") == date(1999, 1, 1)

    def test_year_month(self):
        assert validate.parse_event_date("1999-05") == date(1999, 5, 1)

    def test_year_only(self):
        assert validate.parse_event_date("1999") == date(1999, 1, 1)

    def test_none(self):
        assert validate.parse_event_date(None) is None

    def test_empty(self):
        assert validate.parse_event_date("") is None

    def test_unparseable(self):
        assert validate.parse_event_date("not-a-date") is None

    def test_space_separated_datetime(self):
        assert validate.parse_event_date("1999-05-01 08:00:00") == date(1999, 5, 1)


class TestDedup:
    def test_removes_duplicates(self):
        records = [
            {"gbif_id": 1, "v": "a"},
            {"gbif_id": 2, "v": "b"},
            {"gbif_id": 1, "v": "c"},
        ]
        unique, dups = validate.dedup_by_key(records, "gbif_id")
        assert dups == 1
        assert len(unique) == 2
        assert unique[0]["v"] == "a"  # first kept

    def test_no_duplicates(self):
        records = [{"gbif_id": 1}, {"gbif_id": 2}]
        unique, dups = validate.dedup_by_key(records, "gbif_id")
        assert dups == 0
        assert len(unique) == 2

    def test_missing_key_kept(self):
        records = [{"gbif_id": None}, {"gbif_id": None}, {"gbif_id": 5}]
        unique, dups = validate.dedup_by_key(records, "gbif_id")
        assert dups == 0
        assert len(unique) == 3
