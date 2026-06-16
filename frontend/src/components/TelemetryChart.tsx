"use client";

import { useEffect, useRef } from "react";
import { HistoryPoint } from "../types/telemetry";

export function TelemetryChart({ history }: { history: HistoryPoint[] }) {
  const ref = useRef<HTMLCanvasElement | null>(null);

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
    const padX = 18;
    const padTop = 38;
    const padBottom = 22;
    const plotH = h - padTop - padBottom;

    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "#090c10";
    ctx.fillRect(0, 0, w, h);

    ctx.strokeStyle = "#222b36";
    ctx.lineWidth = 1;

    for (let i = 0; i <= 4; i++) {
      const y = padTop + (plotH * i) / 4;
      ctx.beginPath();
      ctx.moveTo(padX, y);
      ctx.lineTo(w - padX, y);
      ctx.stroke();
    }

    ctx.fillStyle = "#8c98a8";
    ctx.font = "12px Arial";
    ctx.fillText("Speed", 18, 22);

    ctx.fillStyle = "#2ad36b";
    ctx.fillText("Throttle", 76, 22);

    ctx.fillStyle = "#ff5252";
    ctx.fillText("Brake", 154, 22);

    const points = history.slice(-200);

    if (points.length < 2) {
      ctx.fillStyle = "#5e6a7a";
      ctx.fillText("Waiting for live telemetry trace...", 18, 62);
      return;
    }

    function drawLine(
      getter: (point: HistoryPoint) => number,
      max: number,
      color: string,
      width: number
    ) {
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.beginPath();

      points.forEach((point, index) => {
        const x = padX + (index / (points.length - 1)) * (w - padX * 2);
        const normalized = Math.max(0, Math.min(1, getter(point) / max));
        const y = padTop + plotH - normalized * plotH;

        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });

      ctx.stroke();
    }

    drawLine((p) => p.speed_kph, 340, "#4da3ff", 2);
    drawLine((p) => p.throttle * 340, 340, "#2ad36b", 1.6);
    drawLine((p) => p.brake * 340, 340, "#ff5252", 1.6);
  }, [history]);

  return (
    <div className="panel">
      <h3>Telemetry trace</h3>
      <canvas ref={ref} className="chart-canvas" />
    </div>
  );
}