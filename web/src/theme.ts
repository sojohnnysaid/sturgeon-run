// Dark estuary palette. The map is the hero; chrome stays quiet.
export const palette = {
  baseDeep: "#0b1f24", // deepest blue-green — page + map background
  base: "#12343b", // panel surfaces
  baseLine: "#1d4a54", // hairline borders
  water: "#0d262c", // map water fill
  land: "#12343b", // (unused — we render a solid dark base)
  landFill: "#0f2b31", // bundled basemap land polygons (quiet, above the water)
  shoreline: "#245560", // bundled basemap coastline stroke
  riverLine: "#1f6470", // bundled basemap Hudson channel thread
  eelgrass: "#3fbfa0", // occurrences / corridor
  eelgrassLight: "#7fd6b0", // corridor highlight
  sediment: "#e0a458", // quality flags
  station: "#8bd3ff", // stations — distinct cool marker
  text: "#dCECE9",
  textDim: "#7fa39c",
  danger: "#e06a58",
} as const;

export const fonts = {
  display: '"Archivo", system-ui, sans-serif',
  mono: '"IBM Plex Mono", ui-monospace, monospace',
} as const;
