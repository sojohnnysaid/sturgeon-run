#!/usr/bin/env bash
# Sturgeon Run smoke test: verify every service answers, plus MCP auth +
# tools/list + one tools/call. Fails loudly (non-zero) on the first problem.
set -uo pipefail

# Load .env if present so we get MCP_API_TOKEN and ports.
if [[ -f .env ]]; then set -a; # shellcheck disable=SC1091
  source .env; set +a; fi

CORRIDOR_API="${CORRIDOR_API_HOST_URL:-http://localhost:8080}"
TILES="${TILES_HOST_URL:-http://localhost:${MARTIN_PORT:-3000}}"
MCP="${MCP_HOST_URL:-http://localhost:${MCP_PORT:-8081}}/mcp"
WEB="http://localhost:${WEB_PORT:-5173}"
TOKEN="${MCP_API_TOKEN:-}"

fail() { echo "SMOKE FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

echo "== corridor-api =="
curl -fsS "$CORRIDOR_API/healthz" | grep -q '"status":"ok"' || fail "corridor-api /healthz"
ok "/healthz"
curl -fsS "$CORRIDOR_API/api/species" | grep -q 'Acipenser' || fail "corridor-api /api/species"
ok "/api/species"
curl -fsS "$CORRIDOR_API/api/occurrences?limit=1" | grep -q 'FeatureCollection' || fail "occurrences"
ok "/api/occurrences"
curl -fsS "$CORRIDOR_API/api/stations" | grep -q 'FeatureCollection' || fail "stations"
ok "/api/stations"
curl -fsS "$CORRIDOR_API/api/corridor" | grep -q 'FeatureCollection' || fail "corridor"
ok "/api/corridor"

echo "== tiles (Martin) =="
curl -fsS "$TILES/health" >/dev/null 2>&1 || curl -fsS "$TILES/catalog" >/dev/null || fail "tiles catalog/health"
ok "tiles reachable"

echo "== web =="
curl -fsS -o /dev/null "$WEB" || fail "web not serving"
ok "web reachable"

echo "== mcp =="
# 1) No/blank token must be rejected (401) when the endpoint is enabled.
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$MCP" \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}')
if [[ "$code" == "503" ]]; then
  fail "mcp endpoint disabled (MCP_API_TOKEN unset in .env) — set it and restart mcp"
fi
[[ "$code" == "401" ]] || fail "mcp unauthenticated request returned $code, expected 401"
ok "unauthenticated -> 401"

[[ -n "$TOKEN" ]] || fail "MCP_API_TOKEN empty in .env; cannot exercise authorized calls"

# 2) tools/list with token
tools=$(curl -fsS -X POST "$MCP" \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}')
echo "$tools" | grep -q 'list_species' || fail "tools/list missing list_species: $tools"
ok "tools/list"

# 3) one tools/call
res=$(curl -fsS -X POST "$MCP" \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"list_species","arguments":{}}}')
echo "$res" | grep -q 'Acipenser' || fail "tools/call list_species did not return species: $res"
ok "tools/call list_species"

echo "SMOKE PASS: all services healthy, MCP auth + tools/list + tools/call OK"
