import type { LatestReading, StationProps } from "../api";

function esc(s: string): string {
  return s.replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!,
  );
}

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toISOString().slice(0, 16).replace("T", " ") + "Z";
}

// Build the station popup HTML: latest readings matched by site_no / station_id.
export function stationPopupHTML(
  station: StationProps,
  readings: LatestReading[],
): string {
  const mine = readings.filter(
    (r) => r.site_no === station.site_no || r.station_id === station.id,
  );

  const rows = mine
    .map((r) => {
      const val = r.value == null ? "—" : `${r.value}${r.unit ? " " + esc(r.unit) : ""}`;
      return `<li class="popup__reading">
        <b>${esc(r.parameter_name || r.parameter_cd)}</b>
        <span>${val} &middot; ${esc(fmtTime(r.measured_at))}</span>
      </li>`;
    })
    .join("");

  const body = mine.length
    ? `<ul class="popup__readings">${rows}</ul>`
    : `<div class="popup__empty">No latest readings for this station.</div>`;

  return `<div>
    <p class="popup__title">${esc(station.name || station.site_no)}</p>
    <p class="popup__meta">${esc(station.agency_cd)} ${esc(station.site_no)} &middot; ${esc(
      station.site_type_cd || "",
    )}</p>
    ${body}
  </div>`;
}

export function occurrencePopupHTML(props: {
  gbif_id: number;
  event_date: string | null;
  year: number | null;
  basis_of_record: string | null;
  coordinate_uncertainty: number | null;
}): string {
  return `<div>
    <p class="popup__title">Sturgeon occurrence</p>
    <p class="popup__meta">GBIF ${props.gbif_id}</p>
    <ul class="popup__readings">
      <li class="popup__reading"><b>date</b><span>${esc(
        props.event_date || String(props.year ?? "—"),
      )}</span></li>
      <li class="popup__reading"><b>basis</b><span>${esc(
        props.basis_of_record || "—",
      )}</span></li>
      <li class="popup__reading"><b>uncertainty</b><span>${
        props.coordinate_uncertainty == null ? "—" : props.coordinate_uncertainty + " m"
      }</span></li>
    </ul>
  </div>`;
}
