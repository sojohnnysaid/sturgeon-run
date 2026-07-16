import type { StyleSpecification } from "maplibre-gl";
import { palette } from "./theme";
// Bundled at build time (inlined into the JS by Vite's ?raw loader), so the map
// makes NO network request for the basemap — the app stays fully offline-capable.
// Source: Natural Earth 1:10m physical (land + river centerlines), PUBLIC DOMAIN,
// clipped to the Hudson estuary window. See web/scripts/build_basemap.py.
import hudsonRaw from "./basemap/hudson.geojson?raw";

const hudsonBasemap = JSON.parse(hudsonRaw) as GeoJSON.FeatureCollection;

// A self-contained MapLibre style: NO third-party basemap, NO API keys, NO
// external tiles/fonts/CDN. A deep estuary background with a quiet local
// land/coastline reference underneath our data layers, so occurrences,
// stations, and the corridor read against real Hudson geography.
export const baseStyle: StyleSpecification = {
  version: 8,
  sources: {
    basemap: { type: "geojson", data: hudsonBasemap },
  },
  layers: [
    {
      id: "estuary-base",
      type: "background",
      paint: {
        // Deepest tone == open water; land sits slightly lighter on top.
        "background-color": palette.baseDeep,
      },
    },
    {
      id: "basemap-land",
      type: "fill",
      source: "basemap",
      filter: ["==", ["get", "kind"], "land"],
      paint: {
        "fill-color": palette.landFill,
        "fill-opacity": 0.85,
      },
    },
    {
      id: "basemap-shoreline",
      type: "line",
      source: "basemap",
      filter: ["==", ["get", "kind"], "land"],
      paint: {
        "line-color": palette.shoreline,
        "line-width": 0.8,
        "line-opacity": 0.7,
      },
    },
    {
      id: "basemap-river",
      type: "line",
      source: "basemap",
      filter: ["==", ["get", "kind"], "river"],
      paint: {
        // The Hudson channel above the harbor, as a subtle water thread that
        // orients the corridor without competing with the data.
        "line-color": palette.riverLine,
        "line-width": ["interpolate", ["linear"], ["zoom"], 6, 0.6, 12, 2],
        "line-opacity": 0.55,
      },
    },
  ],
};
