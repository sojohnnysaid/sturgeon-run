// corridor-api HTTP client. Uses the global fetch available in Node 22+.
// All MCP tools read through this client; they never touch the DB directly.

const BASE_URL = (
  process.env.CORRIDOR_API_URL || "http://corridor-api:8080"
).replace(/\/+$/, "");

export class CorridorApiError extends Error {
  status: number;
  body: string;
  constructor(status: number, body: string, url: string) {
    super(`corridor-api ${status} for ${url}: ${body}`);
    this.name = "CorridorApiError";
    this.status = status;
    this.body = body;
  }
}

type QueryValue = string | number | undefined | null;

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const url = new URL(BASE_URL + path);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === "") continue;
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

async function getJson<T = unknown>(
  path: string,
  query?: Record<string, QueryValue>,
): Promise<T> {
  const url = buildUrl(path, query);
  const res = await fetch(url, {
    method: "GET",
    headers: { accept: "application/json" },
  });
  const text = await res.text();
  if (!res.ok) {
    throw new CorridorApiError(res.status, text, url);
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new CorridorApiError(res.status, `invalid JSON: ${text}`, url);
  }
}

export const api = {
  baseUrl: BASE_URL,

  listSpecies: () => getJson("/api/species"),

  getOccurrences: (query: {
    from?: string;
    to?: string;
    species_id?: number;
    limit?: number;
  }) => getJson("/api/occurrences", query),

  getStations: () => getJson("/api/stations"),

  getLatestReadings: (query: { parameter_cd?: string }) =>
    getJson("/api/readings/latest", query),

  getCorridorSummary: (query: { species_id?: number }) =>
    getJson("/api/corridor/summary", query),

  getQualityReport: () => getJson("/api/quality-report"),
};
