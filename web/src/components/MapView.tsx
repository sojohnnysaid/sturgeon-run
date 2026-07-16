import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import type {
  FeatureCollection,
  LatestReading,
  OccurrenceProps,
  StationProps,
} from "../api";
import { baseStyle } from "../mapStyle";
import { palette } from "../theme";
import { occurrencePopupHTML, stationPopupHTML } from "./StationPopup";

export interface Visibility {
  occurrences: boolean;
  corridor: boolean;
  stations: boolean;
}

interface Props {
  occurrences: FeatureCollection<OccurrenceProps> | null;
  stations: FeatureCollection<StationProps> | null;
  readings: LatestReading[];
  corridorSourceLayer: string | null;
  corridorMaxCount: number;
  visibility: Visibility;
}

const OCC_SRC = "occurrences";
const STA_SRC = "stations";
const COR_SRC = "corridor";

export default function MapView({
  occurrences,
  stations,
  readings,
  corridorSourceLayer,
  corridorMaxCount,
  visibility,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const loadedRef = useRef(false);
  const readingsRef = useRef<LatestReading[]>(readings);
  const corridorAddedRef = useRef(false);

  // keep latest readings reachable from the (long-lived) click handler
  readingsRef.current = readings;

  // ---- init map once ----
  useEffect(() => {
    if (mapRef.current || !containerRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: baseStyle,
      center: [-73.95, 41.1],
      zoom: 8,
      attributionControl: false,
    });
    mapRef.current = map;

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");

    map.on("load", () => {
      // ---- occurrences (points) ----
      map.addSource(OCC_SRC, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: OCC_SRC,
        type: "circle",
        source: OCC_SRC,
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 6, 4, 12, 8],
          "circle-color": palette.eelgrass,
          "circle-opacity": 0.9,
          "circle-stroke-color": palette.baseDeep,
          "circle-stroke-width": 1,
        },
      });

      // ---- stations (distinct diamond-ish marker) ----
      map.addSource(STA_SRC, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: STA_SRC,
        type: "circle",
        source: STA_SRC,
        paint: {
          "circle-radius": 6,
          "circle-color": palette.station,
          "circle-opacity": 0.95,
          "circle-stroke-color": palette.baseDeep,
          "circle-stroke-width": 2,
        },
      });

      loadedRef.current = true;
      syncData();
      syncCorridor();
      syncVisibility();

      // pointer + popups
      const clickables = [OCC_SRC, STA_SRC];
      clickables.forEach((id) => {
        map.on("mouseenter", id, () => (map.getCanvas().style.cursor = "pointer"));
        map.on("mouseleave", id, () => (map.getCanvas().style.cursor = ""));
      });

      map.on("click", OCC_SRC, (e) => {
        const f = e.features?.[0];
        if (!f) return;
        new maplibregl.Popup({ closeButton: true, maxWidth: "280px" })
          .setLngLat(e.lngLat)
          .setHTML(occurrencePopupHTML(f.properties as unknown as OccurrenceProps))
          .addTo(map);
      });

      map.on("click", STA_SRC, (e) => {
        const f = e.features?.[0];
        if (!f) return;
        const props = f.properties as unknown as StationProps;
        new maplibregl.Popup({ closeButton: true, maxWidth: "300px" })
          .setLngLat(e.lngLat)
          .setHTML(stationPopupHTML(props, readingsRef.current))
          .addTo(map);
      });
    });

    return () => {
      map.remove();
      mapRef.current = null;
      loadedRef.current = false;
      corridorAddedRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- push GeoJSON data into sources ----
  function syncData() {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    if (occurrences) (map.getSource(OCC_SRC) as maplibregl.GeoJSONSource)?.setData(occurrences);
    if (stations) (map.getSource(STA_SRC) as maplibregl.GeoJSONSource)?.setData(stations);
  }

  // ---- add the Martin vector-tile corridor source/layer ----
  function syncCorridor() {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    if (corridorAddedRef.current || !corridorSourceLayer) return;

    // Same-origin tiles through the Vite /tiles proxy (works in compose too).
    map.addSource(COR_SRC, {
      type: "vector",
      tiles: [`${location.origin}/tiles/${corridorSourceLayer}/{z}/{x}/{y}`],
      minzoom: 0,
      maxzoom: 14,
    });

    const max = Math.max(1, corridorMaxCount);
    map.addLayer(
      {
        id: `${COR_SRC}-fill`,
        type: "fill",
        source: COR_SRC,
        "source-layer": corridorSourceLayer,
        paint: {
          "fill-color": [
            "interpolate",
            ["linear"],
            ["coalesce", ["get", "occurrence_count"], 0],
            0,
            palette.base,
            max / 2,
            palette.eelgrass,
            max,
            palette.eelgrassLight,
          ],
          "fill-opacity": 0.45,
        },
      },
      OCC_SRC, // keep corridor beneath the occurrence points
    );
    map.addLayer(
      {
        id: `${COR_SRC}-line`,
        type: "line",
        source: COR_SRC,
        "source-layer": corridorSourceLayer,
        paint: {
          "line-color": palette.eelgrass,
          "line-opacity": 0.5,
          "line-width": 0.6,
        },
      },
      OCC_SRC,
    );
    corridorAddedRef.current = true;
    syncVisibility();
  }

  function syncVisibility() {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    const set = (id: string, on: boolean) => {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", on ? "visible" : "none");
    };
    set(OCC_SRC, visibility.occurrences);
    set(STA_SRC, visibility.stations);
    set(`${COR_SRC}-fill`, visibility.corridor);
    set(`${COR_SRC}-line`, visibility.corridor);
  }

  useEffect(syncData, [occurrences, stations]);
  useEffect(syncCorridor, [corridorSourceLayer, corridorMaxCount]);
  useEffect(syncVisibility, [visibility]);

  return <div className="map" ref={containerRef} />;
}
