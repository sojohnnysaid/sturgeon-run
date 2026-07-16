// corridor-api client. Always fetches at relative /api/* so the browser stays
// same-origin (Vite proxies to corridor-api). No CORS, works in compose too.

export interface OccurrenceProps {
  id: number;
  gbif_id: number;
  event_date: string | null;
  year: number | null;
  basis_of_record: string | null;
  coordinate_uncertainty: number | null;
  dataset_key: string | null;
}

export interface StationProps {
  id: number;
  site_no: string;
  name: string;
  agency_cd: string;
  site_type_cd: string;
}

export type FeatureCollection<P> = {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    geometry: { type: "Point"; coordinates: [number, number] };
    properties: P;
  }>;
};

export interface LatestReading {
  station_id: number;
  site_no: string;
  name: string;
  parameter_cd: string;
  parameter_name: string;
  value: number | null;
  unit: string | null;
  measured_at: string | null;
}

export interface Species {
  id: number;
  gbif_taxon_key: number;
  scientific_name: string;
  common_name: string;
}

export interface QualitySource {
  source: string;
  snapshot_mode: boolean;
  records_fetched: number;
  records_kept: number;
  records_dropped: number;
  drop_reasons: Record<string, number>;
  notes?: string;
  run_at?: string;
}

export interface QualityReport {
  run_id: string | null;
  generated_at: string | null;
  snapshot_mode: boolean;
  sources: QualitySource[];
}

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`${url} -> ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

export function fetchSpecies() {
  return getJSON<Species[]>("/api/species");
}

export function fetchOccurrences(from?: string, to?: string, speciesId?: number) {
  const q = new URLSearchParams();
  if (from) q.set("from", from);
  if (to) q.set("to", to);
  if (speciesId != null) q.set("species_id", String(speciesId));
  q.set("limit", "5000");
  return getJSON<FeatureCollection<OccurrenceProps>>(`/api/occurrences?${q.toString()}`);
}

export function fetchStations() {
  return getJSON<FeatureCollection<StationProps>>("/api/stations");
}

export function fetchLatestReadings() {
  return getJSON<LatestReading[]>("/api/readings/latest");
}

export function fetchQualityReport() {
  return getJSON<QualityReport>("/api/quality-report");
}

// TileJSON for the Martin vector source. We read it to confirm the source
// layer, then serve tiles through the same-origin /tiles proxy.
export interface TileJSON {
  tilejson: string;
  tiles: string[];
  vector_layers?: Array<{ id: string; fields: Record<string, string> }>;
  minzoom?: number;
  maxzoom?: number;
}

export function fetchCorridorTileJSON() {
  return getJSON<TileJSON>("/tiles/corridor_cells");
}

export interface CorridorSummary {
  species_id: number;
  cell_count: number;
  occurrence_count: number;
  hex_meters: number;
  max_cell_count: number;
  computed_at: string;
  bbox: [number, number, number, number];
}

export function fetchCorridorSummary(speciesId?: number) {
  const q = speciesId != null ? `?species_id=${speciesId}` : "";
  return getJSON<CorridorSummary>(`/api/corridor/summary${q}`);
}
