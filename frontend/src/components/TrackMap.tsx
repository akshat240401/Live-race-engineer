"use client";

import { useEffect, useRef } from "react";
import { TelemetrySnapshot, TrackPoint } from "../types/telemetry";

function validPoint(point: TrackPoint): boolean {
  return Number.isFinite(point.x) && Number.isFinite(point.z);
}

function bounds(points: TrackPoint[]) {
  let minX = Infinity;
  let maxX = -Infinity;
  let minZ = Infinity;
  let maxZ = -Infinity;

  points.forEach((point) => {
    minX = Math.min(minX, point.x);
    maxX = Math.max(maxX, point.x);
    minZ = Math.min(minZ, point.z);
    maxZ = Math.max(maxZ, point.z);
  });

  return { minX, maxX, minZ, maxZ };
}

export function TrackMap({ snapshot }: { snapshot: TelemetrySnapshot }) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  const pointCount = snapshot.track_points?.length ?? 0;

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;

    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const w = rect.width;
    const h = rect.height;
    const pad = 26;

    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "#090c10";
    ctx.fillRect(0, 0, w, h);

    const points = (snapshot.track_points || []).filter(validPoint);
    const latest = points.length > 0 ? points[points.length - 1] : null;

    ctx.fillStyle = "#8c98a8";
    ctx.font = "12px Arial";

    if (points.length < 8 || !latest) {
      ctx.fillText("Real track map builds from F1 world-position packets", 16, 26);
      ctx.fillText("Drive part of a lap to draw the circuit shape.", 16, 46);
      return;
    }

    const b = bounds(points);
    const spanX = Math.max(1, b.maxX - b.minX);
    const spanZ = Math.max(1, b.maxZ - b.minZ);
    const scale = Math.min((w - pad * 2) / spanX, (h - pad * 2) / spanZ);
    const drawW = spanX * scale;
    const drawH = spanZ * scale;
    const offsetX = (w - drawW) / 2;
    const offsetY = (h - drawH) / 2;

    function map(point: TrackPoint): { x: number; y: number } {
      return {
        x: offsetX + (point.x - b.minX) * scale,
        y: offsetY + (point.z - b.minZ) * scale,
      };
    }

    // Background grid
    ctx.strokeStyle = "#121821";
    ctx.lineWidth = 1;
    for (let x = pad; x < w; x += 42) {
      ctx.beginPath();
      ctx.moveTo(x, pad);
      ctx.lineTo(x, h - pad);
      ctx.stroke();
    }
    for (let y = pad; y < h; y += 42) {
      ctx.beginPath();
      ctx.moveTo(pad, y);
      ctx.lineTo(w - pad, y);
      ctx.stroke();
    }

    // Full learned track path.
    ctx.strokeStyle = "#252d38";
    ctx.lineWidth = 7;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.beginPath();
    points.forEach((point, index) => {
      const p = map(point);
      if (index === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    });
    ctx.stroke();

    // Latest lap/current segment highlight.
    const currentLap = latest.lap_number;
    const currentLapPoints = points.filter((point) => point.lap_number === currentLap);
    if (currentLapPoints.length > 1) {
      ctx.strokeStyle = "#4da3ff";
      ctx.lineWidth = 3;
      ctx.beginPath();
      currentLapPoints.forEach((point, index) => {
        const p = map(point);
        if (index === 0) ctx.moveTo(p.x, p.y);
        else ctx.lineTo(p.x, p.y);
      });
      ctx.stroke();
    }

    // Start / finish marker from the earliest low-distance point we have.
    const start = [...points].sort((a, b) => a.lap_distance_m - b.lap_distance_m)[0];
    const startP = map(start);
    ctx.strokeStyle = "#d7a64a";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(startP.x - 8, startP.y - 8);
    ctx.lineTo(startP.x + 8, startP.y + 8);
    ctx.moveTo(startP.x + 8, startP.y - 8);
    ctx.lineTo(startP.x - 8, startP.y + 8);
    ctx.stroke();

    // Current car position.
    const car = map(latest);
    ctx.fillStyle = snapshot.connected ? "#2ad36b" : "#ff5252";
    ctx.beginPath();
    ctx.arc(car.x, car.y, 7, 0, Math.PI * 2);
    ctx.fill();

    ctx.strokeStyle = "rgba(255,255,255,.55)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(car.x, car.y, 11, 0, Math.PI * 2);
    ctx.stroke();

    const trackLength = snapshot.track_length_m || 0;
    const progress = trackLength > 0 ? Math.max(0, Math.min(100, (snapshot.lap_distance_m / trackLength) * 100)) : 0;

    ctx.fillStyle = "#8c98a8";
    ctx.font = "12px Arial";
    ctx.fillText(`Track points: ${points.length}`, 16, 24);
    ctx.fillText(`Lap ${snapshot.lap_number || "--"} · ${Math.round(progress)}%`, 16, 42);

    ctx.fillStyle = "#5e6a7a";
    ctx.fillText("Map uses game world X/Z position", 16, h - 16);
  }, [snapshot]);

  return (
    <div className="panel">
      <div className="panel-heading">
        <h3>Live track map</h3>
        <span className={pointCount > 40 ? "state good" : "state"}>
          {pointCount > 40 ? "mapped" : "building"}
        </span>
      </div>
      <canvas ref={ref} className="track-canvas" />
    </div>
  );
}