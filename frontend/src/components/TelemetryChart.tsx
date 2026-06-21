"use client";

import { useEffect, useRef } from "react";

import { HistoryPoint } from "../types/telemetry";

const MAX_RENDERED_POINTS = 6000;

type SampledHistory = {
  points: HistoryPoint[];
  stride: number;
};

function sampledHistory(
  history: HistoryPoint[],
): SampledHistory {
  const stride = Math.max(
    1,
    Math.ceil(
      history.length / MAX_RENDERED_POINTS,
    ),
  );

  if (stride === 1) {
    return {
      points: history,
      stride,
    };
  }

  const points: HistoryPoint[] = [];

  for (
    let index = 0;
    index < history.length;
    index += stride
  ) {
    const point = history[index];

    if (point) {
      points.push(point);
    }
  }

  const lastPoint =
    history[history.length - 1];

  const lastSampledPoint =
    points[points.length - 1];

  if (
    lastPoint &&
    lastSampledPoint !== lastPoint
  ) {
    points.push(lastPoint);
  }

  return {
    points,
    stride,
  };
}

function clamp01(value: number): number {
  return Math.max(
    0,
    Math.min(1, value),
  );
}

function drawTelemetryLine({
  context,
  points,
  getter,
  maxValue,
  color,
  lineWidth,
  padX,
  padTop,
  plotHeight,
  canvasWidth,
}: {
  context: CanvasRenderingContext2D;
  points: HistoryPoint[];
  getter: (
    point: HistoryPoint,
  ) => number;
  maxValue: number;
  color: string;
  lineWidth: number;
  padX: number;
  padTop: number;
  plotHeight: number;
  canvasWidth: number;
}): void {
  if (
    points.length < 2 ||
    maxValue <= 0
  ) {
    return;
  }

  context.strokeStyle = color;
  context.lineWidth = lineWidth;
  context.lineJoin = "round";
  context.lineCap = "round";
  context.beginPath();

  points.forEach(
    (point, index) => {
      const rawValue = getter(point);

      const safeValue = Number.isFinite(
        rawValue,
      )
        ? rawValue
        : 0;

      const normalized = clamp01(
        safeValue / maxValue,
      );

      const denominator = Math.max(
        1,
        points.length - 1,
      );

      const x =
        padX +
        (index / denominator) *
          (canvasWidth - padX * 2);

      const y =
        padTop +
        plotHeight -
        normalized * plotHeight;

      if (index === 0) {
        context.moveTo(x, y);
      } else {
        context.lineTo(x, y);
      }
    },
  );

  context.stroke();
}

export function TelemetryChart({
  history,
}: {
  history: HistoryPoint[];
}) {
  const canvasRef =
    useRef<HTMLCanvasElement | null>(
      null,
    );

  const scrollRef =
    useRef<HTMLDivElement | null>(
      null,
    );

  useEffect(() => {
    const scroller = scrollRef.current;

    if (!scroller) {
      return;
    }

    const scrollContainer: HTMLDivElement =
      scroller;

    function onWheel(
      event: WheelEvent,
    ): void {
      if (
        Math.abs(event.deltaY) <=
        Math.abs(event.deltaX)
      ) {
        return;
      }

      const canScroll =
        scrollContainer.scrollWidth >
        scrollContainer.clientWidth;

      if (!canScroll) {
        return;
      }

      event.preventDefault();

      scrollContainer.scrollLeft +=
        event.deltaY;
    }

    scrollContainer.addEventListener(
      "wheel",
      onWheel,
      {
        passive: false,
      },
    );

    return () => {
      scrollContainer.removeEventListener(
        "wheel",
        onWheel,
      );
    };
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    const scroller = scrollRef.current;

    if (!canvas || !scroller) {
      return;
    }

    const context =
      canvas.getContext("2d");

    if (!context) {
      return;
    }

    const viewport =
      scroller.getBoundingClientRect();

    const devicePixelRatio =
      window.devicePixelRatio || 1;

    const {
      points,
    } = sampledHistory(history);

    const distanceFromRight =
      scroller.scrollWidth -
      scroller.clientWidth -
      scroller.scrollLeft;

    const wasNearRight =
      distanceFromRight < 90;

    const visibleWidth = Math.max(
      320,
      viewport.width,
    );

    const visibleHeight = Math.max(
      190,
      viewport.height || 240,
    );

    const contentWidth =
      points.length > 1
        ? points.length * 3.4
        : visibleWidth;

    const cssWidth = Math.max(
      visibleWidth,
      Math.min(
        24000,
        contentWidth,
      ),
    );

    const cssHeight = visibleHeight;

    canvas.style.width =
      `${cssWidth}px`;

    canvas.style.height =
      `${cssHeight}px`;

    canvas.width = Math.floor(
      cssWidth * devicePixelRatio,
    );

    canvas.height = Math.floor(
      cssHeight * devicePixelRatio,
    );

    context.setTransform(
      devicePixelRatio,
      0,
      0,
      devicePixelRatio,
      0,
      0,
    );

    const canvasWidth = cssWidth;
    const canvasHeight = cssHeight;

    const padX = 18;
    const padTop = 38;
    const padBottom = 28;

    const plotHeight = Math.max(
      40,
      canvasHeight -
        padTop -
        padBottom,
    );

    context.clearRect(
      0,
      0,
      canvasWidth,
      canvasHeight,
    );

    context.fillStyle = "#090c10";

    context.fillRect(
      0,
      0,
      canvasWidth,
      canvasHeight,
    );

    context.strokeStyle =
      "#222b36";

    context.lineWidth = 1;

    for (
      let index = 0;
      index <= 4;
      index += 1
    ) {
      const y =
        padTop +
        (plotHeight * index) / 4;

      context.beginPath();

      context.moveTo(
        padX,
        y,
      );

      context.lineTo(
        canvasWidth - padX,
        y,
      );

      context.stroke();
    }

    const verticalLines = Math.min(
      36,
      Math.max(
        4,
        Math.floor(
          canvasWidth / 240,
        ),
      ),
    );

    context.strokeStyle =
      "rgba(34, 43, 54, 0.55)";

    for (
      let index = 0;
      index <= verticalLines;
      index += 1
    ) {
      const x =
        padX +
        (
          (
            canvasWidth -
            padX * 2
          ) *
          index
        ) /
          verticalLines;

      context.beginPath();

      context.moveTo(
        x,
        padTop,
      );

      context.lineTo(
        x,
        canvasHeight - padBottom,
      );

      context.stroke();
    }

    context.textAlign = "left";
    context.textBaseline =
      "alphabetic";

    context.font = "12px Arial";

    context.fillStyle =
      "#4da3ff";

    context.fillText(
      "Speed",
      18,
      22,
    );

    context.fillStyle =
      "#2ad36b";

    context.fillText(
      "Throttle",
      76,
      22,
    );

    context.fillStyle =
      "#ff5252";

    context.fillText(
      "Brake",
      154,
      22,
    );

    if (points.length < 2) {
      context.fillStyle =
        "#5e6a7a";

      context.font =
        "12px Arial";

      context.fillText(
        "Waiting for live telemetry trace...",
        18,
        62,
      );

      return;
    }

    drawTelemetryLine({
      context,
      points,
      getter: (
        point,
      ) => point.speed_kph,
      maxValue: 340,
      color: "#4da3ff",
      lineWidth: 2,
      padX,
      padTop,
      plotHeight,
      canvasWidth,
    });

    drawTelemetryLine({
      context,
      points,
      getter: (
        point,
      ) => point.throttle,
      maxValue: 1,
      color: "#2ad36b",
      lineWidth: 1.5,
      padX,
      padTop,
      plotHeight,
      canvasWidth,
    });

    drawTelemetryLine({
      context,
      points,
      getter: (
        point,
      ) => point.brake,
      maxValue: 1,
      color: "#ff5252",
      lineWidth: 1.5,
      padX,
      padTop,
      plotHeight,
      canvasWidth,
    });

    const firstPoint = points[0];

    const lastPoint =
      points[points.length - 1];

    const firstTime =
      firstPoint?.session_time ?? 0;

    const lastTime =
      lastPoint?.session_time ??
      firstTime;

    context.fillStyle =
      "#5e6a7a";

    context.font =
      "11px Arial";

    context.textAlign =
      "left";

    context.fillText(
      `${Math.round(firstTime)}s`,
      padX,
      canvasHeight - 9,
    );

    context.textAlign =
      "right";

    context.fillText(
      `${Math.round(lastTime)}s`,
      canvasWidth - padX,
      canvasHeight - 9,
    );

    context.textAlign =
      "left";

    if (wasNearRight) {
      requestAnimationFrame(() => {
        scroller.scrollLeft =
          scroller.scrollWidth;
      });
    }
  }, [history]);

  const stride = Math.max(
    1,
    Math.ceil(
      history.length /
        MAX_RENDERED_POINTS,
    ),
  );

  return (
    <div className="panel telemetry-panel">
      <div className="panel-heading">
        <h3>Telemetry trace</h3>

        <span className="chart-meta">
          scroll wheel inside ·{" "}
          {history.length} pts
          {stride > 1
            ? ` · sampled ${stride}x`
            : ""}
        </span>
      </div>

      <div
        className="chart-scroll"
        ref={scrollRef}
      >
        <canvas
          ref={canvasRef}
          className="chart-canvas"
        />
      </div>
    </div>
  );
}