import type { QualityReport, QualitySource, Species } from "../api";
import TimeFilter from "./TimeFilter";

export interface LayerEntry {
  key: string;
  name: string;
  color: string;
  count: number;
  visible: boolean;
  /** name of the matching quality-report source, if any (e.g. "gbif") */
  qualitySource?: string;
}

interface Props {
  layers: LayerEntry[];
  onToggle: (key: string) => void;
  report: QualityReport | null;
  species: Species[];
  speciesId: number | null;
  onSpeciesChange: (id: number) => void;
  minYear: number;
  maxYear: number;
  fromYear: number;
  toYear: number;
  onTimeChange: (fromYear: number, toYear: number) => void;
  onDownload: () => void;
  downloadDisabled: boolean;
  status: string;
  error: string | null;
}

function Flags({ source, snapshot }: { source?: QualitySource; snapshot: boolean }) {
  if (!source) return null;
  const drops = Object.entries(source.drop_reasons ?? {});
  return (
    <div className="layer__flags">
      {snapshot && <span className="flag flag--snapshot">snapshot-mode</span>}
      <span className="flag flag--ok">kept {source.records_kept}</span>
      <span className={source.records_dropped > 0 ? "flag" : "flag flag--ok"}>
        dropped {source.records_dropped}
      </span>
      {drops.map(([reason, n]) => (
        <span key={reason} className="flag">
          {reason} {n}
        </span>
      ))}
    </div>
  );
}

// The scientist's field log: one entry per layer with live counts, quality
// flags from /api/quality-report, and a visibility toggle. Plus the time
// window control and the GeoJSON export action.
export default function FieldLog({
  layers,
  onToggle,
  report,
  species,
  speciesId,
  onSpeciesChange,
  minYear,
  maxYear,
  fromYear,
  toYear,
  onTimeChange,
  onDownload,
  downloadDisabled,
  status,
  error,
}: Props) {
  const sourceByName = new Map<string, QualitySource>();
  report?.sources.forEach((s) => sourceByName.set(s.source, s));
  const snapshot = report?.snapshot_mode ?? false;

  return (
    <aside className="fieldlog">
      <div className="fieldlog__header">
        <h1 className="fieldlog__title">Sturgeon Run</h1>
        <p className="fieldlog__subtitle">
          Hudson estuary field log
          {report?.run_id ? ` · run ${report.run_id}` : ""}
        </p>
      </div>

      <div className="fieldlog__body">
        {species.length > 0 && (
          <div className="species-picker">
            <label className="fieldlog__section-label" htmlFor="species-select">
              Species
            </label>
            <select
              id="species-select"
              className="species-picker__select"
              value={speciesId ?? ""}
              onChange={(e) => onSpeciesChange(Number(e.target.value))}
            >
              {species.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.common_name
                    ? `${s.common_name} — ${s.scientific_name}`
                    : s.scientific_name}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="fieldlog__section-label">Layers</div>

        {layers.map((l) => (
          <div className="layer" key={l.key}>
            <div className="layer__head">
              <span className="layer__swatch" style={{ background: l.color }} />
              <span className="layer__name">{l.name}</span>
              <span className="layer__count">{l.count}</span>
              <button
                className="layer__toggle"
                data-on={l.visible}
                onClick={() => onToggle(l.key)}
              >
                {l.visible ? "ON" : "OFF"}
              </button>
            </div>
            <Flags
              source={l.qualitySource ? sourceByName.get(l.qualitySource) : undefined}
              snapshot={snapshot}
            />
          </div>
        ))}

        <div className={error ? "status status--error" : "status"}>
          {error ? `error: ${error}` : status}
        </div>
      </div>

      <TimeFilter
        minYear={minYear}
        maxYear={maxYear}
        fromYear={fromYear}
        toYear={toYear}
        onChange={onTimeChange}
      />

      <div style={{ padding: "0 12px 12px" }}>
        <button className="btn" onClick={onDownload} disabled={downloadDisabled}>
          ↓ Export occurrences (GeoJSON)
        </button>
      </div>
    </aside>
  );
}
