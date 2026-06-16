"use client";

import { useEffect, useRef } from "react";
import { HistoryPoint } from "../types/telemetry";

const MAX_RENDERED_POINTS = 6000;

function sampledHistory(history: HistoryPoint[]): { points: HistoryPoint[]; stride: number } {
  const stride = Math.max(1, Math.ceil(history.length / MAX_RENDERED_POINTS));
  if (stride === 1) return { points: history, stride };

  const points: HistoryPoint[] = [];
  for (let index = 0; index < history.length; index += stride) {
    points.push(history[index]);
  }

  const last = history[history.length - 1];
  if (last && points[points.length - 1] !== last) points.push(last);

  return { points, stride };
}

export function TelemetryChart({ history }: { history: HistoryPoint[] }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const scroller = scrollRef.current;
    if (!scroller) return;

    function onWheel(event: WheelEvent) {
      if (!scroller) return;
      if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;

      const canScroll = scroller.scrollWidth > scroller.clientWidth;
      if (!canScroll) return;

      event.preventDefault();
      scroller.scrollLeft += event.deltaY;
    }

    scroller.addEventListener("wheel", onWheel, { passive: false });
    return () => scroller.removeEventListener("wheel", onWheel);
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    const scroller = scrollRef.current;
    if (!canvas || !scroller) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const viewport = scroller.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const { points } = sampledHistory(history);

    const wasNearRight = scroller.scrollWidth - scroller.clientWidth - scroller.scrollLeft < 90;
    const visibleWidth = Math.max(320, viewport.width);
    const visibleHeight = Math.max(190, viewport.height || 240);
    const cssWidth = Math.max(visibleWidth, Math.min(24000, points.length * 3.4));
    const cssHeight = visibleHeight;

    canvas.style.width = `${cssWidth}px`;
    canvas.style.height = `${cssHeight}px`;
    canvas.width = Math.floor(cssWidth * dpr);
    canvas.height = Math.floor(cssHeight * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const w = cssWidth;
    const h = cssHeight;
    const padX = 18;
    const padTop = 38;
    const padBottom = 28;
    const plotH = Math.max(40, h - padTop - padBottom);

    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "#090c10";
    ctx.fillRect(0, 0, w, h);

    ctx.strokeStyle = "#222b36";
    ctx.lineWidth = 1;

    for (let i = 0; i <= 4; i += 1) {
      const y = padTop + (plotH * i) / 4;
      ctx.beginPath();
      ctx.moveTo(padX, y);
      ctx.lineTo(w - padX, y);
      ctx.stroke();
    }

    const verticalLines = Math.min(36, Math.max(4, Math.floor(w / 240)));
    ctx.strokeStyle = "rgba(34, 43, 54, 0.55)";
    for (let i = 0; i <= verticalLines; i += 1) {
      const x = padX + ((w - padX * 2) * i) / verticalLines;
      ctx.beginPath();
      ctx.moveTo(x, padTop);
      ctx.lineTo(x, h - padBottom);
      ctx.stroke();
    }

    ctx.fillStyle = "#8c98a8";
    ctx.font = "12px Arial";
    ctx.fillText("Speed", 18, 22);
    ctx.fillStyle = "#2ad36b";
    ctx.fillText("Throttle", 76, 22);
    ctx.fillStyle = "#ff5252";
    ctx.fillText("Brake", 154, 22);

    if (points.length < 2) {
      ctx.fillStyle = "#5e6a7a";
      ctx.fillText("Waiting for live telemetry trace...", 18, 62);
      return;
    }

    function xAt(index: number): number {
      return padX + (index / (points.length - 1)) * (w - padX * 2);
    }

    function drawLine(getter: (point: HistoryPoint) => number, max: number, color: string, width: number) {
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.beginPath();

      points.forEach((point, index) => {
        const normalized = Math.max(0, Math.min(1, getter(point) / max));
        const x = xAt(index);
        const y = padTop + plotH - normalized * plotH;
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });

      ctx.stroke();
    }

    drawLine((p) => p.speed_kph, 340, "#4da3ff", 2);
    drawLine((p) => p.throttle * 340, 340, "#2ad36b", 1.5);
    drawLine((p) => p.brake * 340, 340, "#ff5252", 1.5);

    const firstTime = points[0]?.session_time ?? 0;
    const lastTime = points[points.length - 1]?.session_time ?? firstTime;
    ctx.fillStyle = "#5e6a7a";
    ctx.font = "11px Arial";
    ctx.fillText(`${Math.round(firstTime)}s`, padX, h - 9);
    ctx.textAlign = "right";
    ctx.fillText(`${Math.round(lastTime)}s`, w - padX, h - 9);
    ctx.textAlign = "left";

    if (wasNearRight) {
      scroller.scrollLeft = scroller.scrollWidth;
    }
  }, [history]);

  const stride = Math.max(1, Math.ceil(history.length / MAX_RENDERED_POINTS));

  return (
    <div className="panel telemetry-panel">
      <div className="panel-heading">
        <h3>Telemetry trace</h3>
        <span className="chart-meta">
          scroll wheel inside · {history.length} pts{stride > 1 ? ` · sampled ${stride}x` : ""}
        </span>
      </div>
      <div className="chart-scroll" ref={scrollRef}>
        <canvas ref={canvasRef} className="chart-canvas" />
      </div>
    </div>
  );
}