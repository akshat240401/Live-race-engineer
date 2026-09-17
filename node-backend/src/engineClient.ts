import WebSocket from "ws";

export type JsonObject = Record<string, unknown>;

type SnapshotListener = (snapshot: JsonObject) => void;
type StatusListener = (connected: boolean) => void;

export class EngineStreamClient {
  private socket: WebSocket | null = null;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private stopped = false;
  private latest: JsonObject | null = null;
  private latestAtMs: number | null = null;
  private connected = false;

  constructor(
    private readonly wsUrl: string,
    private readonly reconnectMs: number,
    private readonly onSnapshot: SnapshotListener,
    private readonly onStatus: StatusListener,
  ) {}

  start(): void {
    this.stopped = false;
    this.connect();
  }

  stop(): void {
    this.stopped = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.socket?.close();
    this.socket = null;
    this.setConnected(false);
  }

  get latestSnapshot(): JsonObject | null {
    return this.latest;
  }

  get latestSnapshotAgeMs(): number | null {
    return this.latestAtMs === null ? null : Date.now() - this.latestAtMs;
  }

  get isConnected(): boolean {
    return this.connected;
  }

  private connect(): void {
    if (this.stopped) return;

    const socket = new WebSocket(this.wsUrl);
    this.socket = socket;

    socket.on("open", () => {
      if (this.socket !== socket) return;
      this.setConnected(true);
      console.log(`[node-backend] connected to telemetry engine ${this.wsUrl}`);
    });

    socket.on("message", (data) => {
      try {
        const decoded = JSON.parse(data.toString()) as JsonObject;
        this.latest = decoded;
        this.latestAtMs = Date.now();
        this.onSnapshot(decoded);
      } catch (error) {
        console.error("[node-backend] invalid telemetry JSON from engine", error);
      }
    });

    socket.on("close", () => {
      if (this.socket === socket) this.socket = null;
      this.setConnected(false);
      this.scheduleReconnect();
    });

    socket.on("error", (error) => {
      console.error(`[node-backend] telemetry engine WebSocket error: ${error.message}`);
    });
  }

  private scheduleReconnect(): void {
    if (this.stopped || this.reconnectTimer) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, this.reconnectMs);
  }

  private setConnected(next: boolean): void {
    if (this.connected === next) return;
    this.connected = next;
    this.onStatus(next);
  }
}
