import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchCorridorSummary,
  fetchCorridorTileJSON,
  fetchOccurrences,
  fetchLatestReadings,
  fetchQualityReport,
  fetchSpecies,
  fetchStations,
  type FeatureCollection,
  type LatestReading,
  type OccurrenceProps,
  type QualityReport,
  type Species,
  type StationProps,
} from "./api";
import MapView, { type Visibility } from "./components/MapView";
import FieldLog, { type LayerEntry } from "./components/FieldLog";
import { palette } from "./theme";

// Occurrences span ~1815–2026 in the loaded data; we derive the real range
// from the fetched features and only fall back to these if empty.
const FALLBACK_MIN = 2003;
const FALLBACK_MAX = 2026;

export default function App() {
  const [occurrences, setOccurrences] =
    useState<FeatureCollection<OccurrenceProps> | null>(null);
  const [stations, setStations] = useState<FeatureCollection<StationProps> | null>(null);
  const [readings, setReadings] = useState<LatestReading[]>([]);
  const [report, setReport] = useState<QualityReport | null>(null);
  const [corridorLayer, setCorridorLayer] = useState<string | null>(null);
  const [corridorMax, setCorridorMax] = useState(1);
  const [corridorCells, setCorridorCells] = useState(0);

  // Multi-species: the field log has a picker; occurrences + corridor are
  // fetched/filtered per selected species_id.
  const [species, setSpecies] = useState<Species[]>([]);
  const [speciesId, setSpeciesId] = useState<number | null>(null);

  const [minYear, setMinYear] = useState(FALLBACK_MIN);
  const [maxYear, setMaxYear] = useState(FALLBACK_MAX);
  const [fromYear, setFromYear] = useState(FALLBACK_MIN);
  const [toYear, setToYear] = useState(FALLBACK_MAX);
  const rangeInit = useRef(false);

  const [visibility, setVisibility] = useState<Visibility>({
    occurrences: true,
    corridor: true,
    stations: true,
  });

  const [status, setStatus] = useState("loading…");
  const [error, setError] = useState<string | null>(null);

  // ---- initial, non-time/species-filtered loads ----
  useEffect(() => {
    (async () => {
      try {
        const [sta, rd, rep, tj, spp] = await Promise.all([
          fetchStations(),
          fetchLatestReadings(),
          fetchQualityReport(),
          fetchCorridorTileJSON().catch(() => null),
          fetchSpecies().catch(() => [] as Species[]),
        ]);
        setStations(sta);
        setReadings(rd);
        setReport(rep);
        if (tj?.vector_layers?.length) setCorridorLayer(tj.vector_layers[0].id);
        else setCorridorLayer("corridor_cells");
        setSpecies(spp);
        if (spp.length) setSpeciesId((cur) => cur ?? spp[0].id);
      } catch (e) {
        setError(String(e instanceof Error ? e.message : e));
      }
    })();
  }, []);

  // ---- corridor summary per selected species (drives coloring + count) ----
  useEffect(() => {
    if (speciesId == null) return;
    let cancelled = false;
    (async () => {
      const sum = await fetchCorridorSummary(speciesId).catch(() => null);
      if (cancelled) return;
      setCorridorMax(sum?.max_cell_count ? sum.max_cell_count : 1);
      setCorridorCells(sum?.cell_count ?? 0);
    })();
    return () => {
      cancelled = true;
    };
  }, [speciesId]);

  // ---- occurrences: initial + refetch on time or species change ----
  useEffect(() => {
    if (speciesId == null) return;
    let cancelled = false;
    (async () => {
      try {
        setStatus("fetching occurrences…");
        // Only pass date bounds once the range is initialized for this species.
        const from = rangeInit.current ? `${fromYear}-01-01` : undefined;
        const to = rangeInit.current ? `${toYear}-12-31` : undefined;
        const fc = await fetchOccurrences(from, to, speciesId);
        if (cancelled) return;
        setOccurrences(fc);

        // derive the real year range from the data on first load
        if (!rangeInit.current) {
          const years = fc.features
            .map((f) => f.properties.year)
            .filter((y): y is number => typeof y === "number");
          if (years.length) {
            const lo = Math.min(...years);
            const hi = Math.max(...years);
            setMinYear(lo);
            setMaxYear(hi);
            setFromYear(lo);
            setToYear(hi);
          }
          rangeInit.current = true;
        }
        setStatus(`${fc.features.length} occurrences in window`);
        setError(null);
      } catch (e) {
        if (!cancelled) setError(String(e instanceof Error ? e.message : e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [fromYear, toYear, speciesId]);

  const onTimeChange = useCallback((f: number, t: number) => {
    if (f > t) return; // keep from <= to
    setFromYear(f);
    setToYear(t);
  }, []);

  const onSpeciesChange = useCallback((id: number) => {
    // Recompute the year range for the newly selected species on next fetch.
    rangeInit.current = false;
    setSpeciesId(id);
  }, []);

  const onToggle = useCallback((key: string) => {
    setVisibility((v) => ({ ...v, [key]: !v[key as keyof Visibility] }));
  }, []);

  // ---- GeoJSON export of the currently-shown occurrences ----
  const onDownload = useCallback(() => {
    if (!occurrences) return;
    const blob = new Blob([JSON.stringify(occurrences, null, 2)], {
      type: "application/geo+json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `sturgeon-occurrences_${fromYear}-${toYear}.geojson`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }, [occurrences, fromYear, toYear]);

  const layers: LayerEntry[] = useMemo(
    () => [
      {
        key: "occurrences",
        name: "Occurrences",
        color: palette.eelgrass,
        count: occurrences?.features.length ?? 0,
        visible: visibility.occurrences,
        qualitySource: "gbif",
      },
      {
        key: "corridor",
        name: "Corridor (hex density)",
        color: palette.eelgrassLight,
        count: corridorCells,
        visible: visibility.corridor,
      },
      {
        key: "stations",
        name: "USGS stations",
        color: palette.station,
        count: stations?.features.length ?? 0,
        visible: visibility.stations,
        qualitySource: "usgs",
      },
    ],
    [occurrences, stations, corridorCells, visibility],
  );

  return (
    <div className="app">
      <MapView
        occurrences={occurrences}
        stations={stations}
        readings={readings}
        corridorSourceLayer={corridorLayer}
        corridorMaxCount={corridorMax}
        corridorSpeciesId={speciesId}
        visibility={visibility}
      />
      <FieldLog
        layers={layers}
        onToggle={onToggle}
        report={report}
        species={species}
        speciesId={speciesId}
        onSpeciesChange={onSpeciesChange}
        minYear={minYear}
        maxYear={maxYear}
        fromYear={fromYear}
        toYear={toYear}
        onTimeChange={onTimeChange}
        onDownload={onDownload}
        downloadDisabled={!occurrences}
        status={status}
        error={error}
      />
    </div>
  );
}
