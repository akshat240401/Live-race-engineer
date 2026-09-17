import "dotenv/config";

export type GatewayConfig = {
  port: number;
  engineHttpBase: string;
  engineWsUrl: string;
  corsOrigins: string[];
  reconnectMs: number;
};

function positiveInt(value: string | undefined, fallback: number): number {
  if (!value) return fallback;
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export function loadConfig(): GatewayConfig {
  const port = positiveInt(process.env.PORT, 8080);
  const engineHttpBase = (process.env.PYTHON_ENGINE_HTTP || "http://127.0.0.1:8000")
    .replace(/\/$/, "");
  const engineWsUrl =
    process.env.PYTHON_ENGINE_WS || "ws://127.0.0.1:8000/ws/live?hz=30";
  const corsOrigins = (process.env.CORS_ORIGINS || "http://localhost:3000,http://127.0.0.1:3000")
    .split(",")
    .map((origin) => origin.trim())
    .filter(Boolean);
  const reconnectMs = positiveInt(process.env.UPSTREAM_RECONNECT_MS, 1000);

  return {
    port,
    engineHttpBase,
    engineWsUrl,
    corsOrigins,
    reconnectMs,
  };
}
