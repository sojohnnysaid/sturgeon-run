// Sturgeon Run MCP server.
// Stateless MCP over Streamable HTTP JSON-RPC 2.0, single endpoint POST /mcp.
// Non-streaming application/json responses are valid for this transport.

import express, { type Request, type Response } from "express";
import { ZodError } from "zod";
import { getTool, listToolsPayload } from "./tools.js";
import { CorridorApiError, api } from "./api.js";

const PORT = Number(process.env.MCP_PORT || 8081);
const API_TOKEN = process.env.MCP_API_TOKEN || "";
const SERVER_NAME = "sturgeon-run-mcp";
const SERVER_VERSION = process.env.npm_package_version || "0.1.0";
const PROTOCOL_VERSION = "2024-11-05";

// JSON-RPC 2.0 error codes.
const PARSE_ERROR = -32700;
const INVALID_REQUEST = -32600;
const METHOD_NOT_FOUND = -32601;
const INVALID_PARAMS = -32602;
const INTERNAL_ERROR = -32603;

type JsonRpcId = string | number | null;

function rpcResult(id: JsonRpcId, result: unknown) {
  return { jsonrpc: "2.0", id, result };
}

function rpcError(
  id: JsonRpcId,
  code: number,
  message: string,
  data?: unknown,
) {
  const error: { code: number; message: string; data?: unknown } = {
    code,
    message,
  };
  if (data !== undefined) error.data = data;
  return { jsonrpc: "2.0", id, error };
}

async function handleRpc(body: unknown): Promise<object> {
  if (
    typeof body !== "object" ||
    body === null ||
    (body as { jsonrpc?: unknown }).jsonrpc !== "2.0"
  ) {
    return rpcError(null, INVALID_REQUEST, "Invalid JSON-RPC 2.0 request");
  }

  const { id = null, method, params } = body as {
    id?: JsonRpcId;
    method?: unknown;
    params?: unknown;
  };

  if (typeof method !== "string") {
    return rpcError(id, INVALID_REQUEST, "Missing or invalid 'method'");
  }

  switch (method) {
    case "initialize":
      return rpcResult(id, {
        protocolVersion: PROTOCOL_VERSION,
        capabilities: { tools: {} },
        serverInfo: { name: SERVER_NAME, version: SERVER_VERSION },
      });

    case "ping":
      return rpcResult(id, {});

    case "tools/list":
      return rpcResult(id, { tools: listToolsPayload() });

    case "tools/call": {
      const p = (params ?? {}) as { name?: unknown; arguments?: unknown };
      if (typeof p.name !== "string") {
        return rpcError(id, INVALID_PARAMS, "params.name (string) is required");
      }
      const tool = getTool(p.name);
      if (!tool) {
        return rpcError(id, METHOD_NOT_FOUND, `Unknown tool: ${p.name}`);
      }
      // Validate arguments against the tool's zod schema.
      const parsed = tool.schema.safeParse(p.arguments ?? {});
      if (!parsed.success) {
        return rpcError(
          id,
          INVALID_PARAMS,
          `Invalid arguments for tool ${p.name}`,
          (parsed.error as ZodError).flatten(),
        );
      }
      try {
        const result = await tool.handler(parsed.data);
        return rpcResult(id, {
          content: [{ type: "text", text: JSON.stringify(result) }],
        });
      } catch (err) {
        if (err instanceof CorridorApiError) {
          return rpcError(id, INTERNAL_ERROR, "corridor-api request failed", {
            status: err.status,
            body: err.body,
          });
        }
        const message = err instanceof Error ? err.message : String(err);
        return rpcError(id, INTERNAL_ERROR, message);
      }
    }

    default:
      return rpcError(id, METHOD_NOT_FOUND, `Unknown method: ${method}`);
  }
}

const app = express();
app.use(express.json({ limit: "1mb" }));

// Liveness probe (not part of the MCP contract, handy for compose healthchecks).
app.get("/healthz", (_req: Request, res: Response) => {
  res.json({ status: "ok", corridor_api: api.baseUrl });
});

app.post("/mcp", async (req: Request, res: Response) => {
  // Fail-closed auth. No token configured => endpoint disabled (503).
  if (!API_TOKEN) {
    res
      .status(503)
      .json({ error: "MCP endpoint disabled: MCP_API_TOKEN is not set" });
    return;
  }

  const auth = req.header("authorization") || "";
  const expected = `Bearer ${API_TOKEN}`;
  if (auth !== expected) {
    res
      .status(401)
      .json({ error: "Unauthorized: missing or invalid bearer token" });
    return;
  }

  // Body must be valid JSON (express.json already parsed it).
  if (req.body === undefined || req.body === null) {
    res.status(200).json(rpcError(null, PARSE_ERROR, "Parse error"));
    return;
  }

  try {
    const response = await handleRpc(req.body);
    res.status(200).json(response);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    res.status(200).json(rpcError(null, INTERNAL_ERROR, message));
  }
});

// Malformed JSON body handler for express.json parse failures.
app.use(
  (
    err: Error & { type?: string },
    req: Request,
    res: Response,
    next: express.NextFunction,
  ) => {
    if (err && err.type === "entity.parse.failed") {
      // Only meaningful on /mcp; still enforce auth gate order.
      if (!API_TOKEN) {
        res.status(503).json({ error: "MCP endpoint disabled" });
        return;
      }
      const auth = req.header("authorization") || "";
      if (auth !== `Bearer ${API_TOKEN}`) {
        res.status(401).json({ error: "Unauthorized" });
        return;
      }
      res.status(200).json(rpcError(null, PARSE_ERROR, "Parse error"));
      return;
    }
    next(err);
  },
);

app.listen(PORT, () => {
  const authState = API_TOKEN ? "enabled (bearer required)" : "DISABLED (503)";
  // eslint-disable-next-line no-console
  console.log(
    `[${SERVER_NAME}] listening on :${PORT}  POST /mcp  auth=${authState}  corridor-api=${api.baseUrl}`,
  );
});
