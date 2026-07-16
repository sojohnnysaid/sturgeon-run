import type { StyleSpecification } from "maplibre-gl";
import { palette } from "./theme";

// A self-contained MapLibre style: NO third-party basemap, NO API keys.
// Just a solid dark estuary background. Our own data renders on top.
export const baseStyle: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [
    {
      id: "estuary-base",
      type: "background",
      paint: {
        "background-color": palette.baseDeep,
      },
    },
  ],
};
