// Tool definitions: zod input schemas + handlers. Every handler reads through
// the corridor-api client (never the DB directly).

import { z } from "zod";
import { zodToJsonSchema } from "zod-to-json-schema";
import { api } from "./api.js";

export interface ToolDefinition {
  name: string;
  description: string;
  schema: z.ZodTypeAny;
  handler: (args: unknown) => Promise<unknown>;
}

// --- schemas ------------------------------------------------------------

const emptySchema = z.object({}).strict();

const bboxSchema = z
  .tuple([z.number(), z.number(), z.number(), z.number()])
  .describe("[minLon, minLat, maxLon, maxLat]");

const getOccurrencesSchema = z
  .object({
    bbox: bboxSchema.optional(),
    from: z.string().optional().describe("start date YYYY-MM-DD"),
    to: z.string().optional().describe("end date YYYY-MM-DD"),
    species_id: z.number().int().optional(),
    limit: z.number().int().positive().optional(),
  })
  .strict();

const getLatestReadingsSchema = z
  .object({
    parameter_cd: z
      .string()
      .optional()
      .describe("USGS parameter code filter, e.g. 00010 (water temp)"),
  })
  .strict();

const getCorridorSummarySchema = z
  .object({
    species_id: z.number().int().optional(),
  })
  .strict();

// --- bbox filter helper -------------------------------------------------

interface GeoFeature {
  geometry?: { type?: string; coordinates?: unknown };
  [k: string]: unknown;
}
interface FeatureCollection {
  type?: string;
  features?: GeoFeature[];
  [k: string]: unknown;
}

function filterFeaturesByBbox(
  fc: FeatureCollection,
  bbox: [number, number, number, number],
): FeatureCollection {
  const [minLon, minLat, maxLon, maxLat] = bbox;
  const features = Array.isArray(fc.features) ? fc.features : [];
  const kept = features.filter((f) => {
    const coords = f.geometry?.coordinates;
    if (!Array.isArray(coords) || coords.length < 2) return false;
    const lon = Number(coords[0]);
    const lat = Number(coords[1]);
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) return false;
    return lon >= minLon && lon <= maxLon && lat >= minLat && lat <= maxLat;
  });
  return { ...fc, features: kept };
}

// --- tool table ---------------------------------------------------------

export const tools: ToolDefinition[] = [
  {
    name: "list_species",
    description:
      "List all sturgeon species tracked in the corridor (GET /api/species).",
    schema: emptySchema,
    handler: async () => api.listSpecies(),
  },
  {
    name: "get_occurrences",
    description:
      "Get sturgeon occurrence points as a GeoJSON FeatureCollection " +
      "(GET /api/occurrences). Optional from/to (YYYY-MM-DD), species_id, and " +
      "limit are passed to corridor-api. corridor-api has NO bbox param: if a " +
      "bbox [minLon,minLat,maxLon,maxLat] is supplied, features are filtered " +
      "to that box client-side after fetching.",
    schema: getOccurrencesSchema,
    handler: async (args) => {
      const a = args as z.infer<typeof getOccurrencesSchema>;
      const fc = (await api.getOccurrences({
        from: a.from,
        to: a.to,
        species_id: a.species_id,
        limit: a.limit,
      })) as FeatureCollection;
      if (a.bbox) return filterFeaturesByBbox(fc, a.bbox);
      return fc;
    },
  },
  {
    name: "get_stations",
    description:
      "List USGS monitoring stations as a GeoJSON FeatureCollection " +
      "(GET /api/stations).",
    schema: emptySchema,
    handler: async () => api.getStations(),
  },
  {
    name: "get_latest_readings",
    description:
      "Get the latest sensor reading per station/parameter " +
      "(GET /api/readings/latest). Optional parameter_cd filters by USGS " +
      "parameter code (e.g. 00010 water temperature).",
    schema: getLatestReadingsSchema,
    handler: async (args) => {
      const a = args as z.infer<typeof getLatestReadingsSchema>;
      return api.getLatestReadings({ parameter_cd: a.parameter_cd });
    },
  },
  {
    name: "get_corridor_summary",
    description:
      "Get the corridor summary (cell_count, occurrence_count, hex_meters, " +
      "bbox, etc.) for a species (GET /api/corridor/summary). Optional " +
      "species_id.",
    schema: getCorridorSummarySchema,
    handler: async (args) => {
      const a = args as z.infer<typeof getCorridorSummarySchema>;
      return api.getCorridorSummary({ species_id: a.species_id });
    },
  },
  {
    name: "get_data_quality_report",
    description:
      "Get the latest ingest run's data-quality report with per-source " +
      "record counts and drop reasons (GET /api/quality-report).",
    schema: emptySchema,
    handler: async () => api.getQualityReport(),
  },
];

const toolsByName = new Map(tools.map((t) => [t.name, t]));

export function getTool(name: string): ToolDefinition | undefined {
  return toolsByName.get(name);
}

// tools/list payload: name, description, JSON-Schema inputSchema derived from zod.
export function listToolsPayload() {
  return tools.map((t) => ({
    name: t.name,
    description: t.description,
    inputSchema: zodToJsonSchema(t.schema, { target: "jsonSchema7" }),
  }));
}
