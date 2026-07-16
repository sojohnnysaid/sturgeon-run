-- Sturgeon Run — spatial + query indexes
CREATE INDEX IF NOT EXISTS occurrences_geom_gix   ON occurrences   USING GIST (geom);
CREATE INDEX IF NOT EXISTS occurrences_date_idx    ON occurrences   (event_date);
CREATE INDEX IF NOT EXISTS occurrences_species_idx ON occurrences   (species_id);
CREATE INDEX IF NOT EXISTS stations_geom_gix        ON stations      USING GIST (geom);
CREATE INDEX IF NOT EXISTS readings_station_idx     ON readings      (station_id, parameter_cd, measured_at DESC);
CREATE INDEX IF NOT EXISTS corridor_geom_gix        ON corridor_cells USING GIST (geom);
CREATE INDEX IF NOT EXISTS corridor_species_idx     ON corridor_cells (species_id);
CREATE INDEX IF NOT EXISTS dqr_run_idx              ON data_quality_reports (run_id, source);
