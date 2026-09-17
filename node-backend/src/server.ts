import http from "node:http";

import cors from "cors";
import express, { type Request, type Response } from "express";
import { WebSocket, WebSocketServer } from "ws";

import { loadConfig } from "./config.js";
import { EngineStreamClient, type JsonObject } from "./engineClient.js";

const config = loadConfig();
const app = express();
app.disable("x-powered-by");
app.use(
  cors({
    origin(origin, callback) {
      if (!origin || config.corsOrigins.includes(origin)) return callback(null, true);
      callback(new Error(`Origin ${origin} is not allowed`));
    },
    credentials: true,
  }),
);
app.use(express.json({ limit: "1mb" }));

const server = http.createServer(app);
const browserWs = new WebSocketServer({ server, path: "/ws/live" });

let browserConnections = 0;
let upstreamConnected = false;

function broadcast(snapshot: JsonObject): void {
  const encoded = JSON.stringify(snapshot);
  for (const client of browserWs.clients) {
    if (client.readyState === WebSocket.OPEN) client.send(encoded);
  }
}

const engine = new EngineStreamClient(
  config.engineWsUrl,
  config.reconnectMs,
  broadcast,
  (connected) => {
    upstreamConnected = connected;
  },
);

browserWs.on("connection", (socket) => {
  browserConnections += 1;
  const snapshot = engine.latestSnapshot;
  if (snapshot && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(snapshot));
  }
  socket.on("close", () => {
    browserConnections = Math.max(0, browserConnections - 1);
  });
});

app.get("/", (_req, res) => {
  res.json({
    name: "Live Race Engineer Node Backend",
    runtime: "Node.js + TypeScript",
    telemetry_engine: config.engineHttpBase,
    ws: "/ws/live",
    api: "/api/*",
  });
});

app.get("/api/state", async (_req, res) => {
  if (engine.latestSnapshot) {
    res.json(engine.latestSnapshot);
    return;
  }
  await proxyToEngine(_req, res);
});

app.get("/api/health", async (req, res) => {
  try {
    const upstream = await fetch(`${config.engineHttpBase}/api/health`, {
      headers: forwardedHeaders(req),
      signal: AbortSignal.timeout(2500),
    });
    const body = await readJsonOrText(upstream);
    if (!upstream.ok) {
      res.status(upstream.status).send(body);
      return;
    }

    const upstreamBody = isObject(body) ? body : { engine_response: body };
    res.json({
      ...upstreamBody,
      node_backend: true,
      node_backend_runtime: process.version,
      engine_ws_connected: upstreamConnected,
      browser_ws_clients: browserConnections,
      node_snapshot_age_ms: engine.latestSnapshotAgeMs,
    });
  } catch (error) {
    res.status(503).json({
      ok: false,
      node_backend: true,
      engine_ws_connected: upstreamConnected,
      browser_ws_clients: browserConnections,
      node_snapshot_age_ms: engine.latestSnapshotAgeMs,
      detail: error instanceof Error ? error.message : "Telemetry engine unavailable",
    });
  }
});

app.all(/^\/api\//, proxyToEngine);

async function proxyToEngine(req: Request, res: Response): Promise<void> {
  const target = `${config.engineHttpBase}${req.originalUrl}`;
  const method = req.method.toUpperCase();
  const hasBody = method !== "GET" && method !== "HEAD" && req.body !== undefined;

  try {
    const upstream = await fetch(target, {
      method,
      headers: forwardedHeaders(req, hasBody),
      body: hasBody ? JSON.stringify(req.body) : undefined,
      signal: AbortSignal.timeout(15_000),
    });

    const contentType = upstream.headers.get("content-type");
    if (contentType) res.setHeader("content-type", contentType);
    const payload = Buffer.from(await upstream.arrayBuffer());
    res.status(upstream.status).send(payload);
  } catch (error) {
    res.status(502).json({
      detail: error instanceof Error ? error.message : "Telemetry engine request failed",
    });
  }
}

function forwardedHeaders(req: Request, jsonBody = false): Record<string, string> {
  const headers: Record<string, string> = {
    accept: req.header("accept") || "application/json",
  };
  if (jsonBody) headers["content-type"] = "application/json";
  return headers;
}

async function readJsonOrText(response: globalThis.Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return {};
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

server.listen(config.port, "127.0.0.1", () => {
  console.log(`[node-backend] listening on http://localhost:${config.port}`);
  console.log(`[node-backend] proxying REST to ${config.engineHttpBase}`);
  console.log(`[node-backend] consuming telemetry from ${config.engineWsUrl}`);
  engine.start();
});

function shutdown(): void {
  engine.stop();
  browserWs.close();
  server.close(() => process.exit(0));
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
