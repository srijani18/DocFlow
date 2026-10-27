"use client";

import { useState } from "react";

const DAY = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", timeZone: "UTC" });

export type DayCount = { date: string; uploaded: number };

function dayLabel(date: string) {
  return DAY.format(new Date(`${date}T00:00:00Z`));
}

/** Documents uploaded per day (F13 AC2): one series, so no legend; the hovered day is named
 * above the bars, and a table carries the same numbers for screen readers. */
export function VolumeChart({ days }: { days: DayCount[] }) {
  const [hovered, setHovered] = useState<number | null>(null);
  const max = Math.max(1, ...days.map((day) => day.uploaded));
  const total = days.reduce((sum, day) => sum + day.uploaded, 0);
  const shown = hovered === null ? null : days[hovered];
  return (
    <figure>
      <figcaption className="mb-3 flex items-baseline justify-between gap-4 text-sm">
        <span className="font-medium">Documents uploaded per day</span>
        <span className="text-muted-foreground tabular-nums" aria-live="polite">
          {shown ? `${dayLabel(shown.date)}: ${shown.uploaded}` : `${total} in total`}
        </span>
      </figcaption>
      <div className="relative" aria-hidden>
        <span className="absolute -top-1 left-0 text-xs text-muted-foreground tabular-nums">
          {max}
        </span>
        <div
          className="ml-8 flex h-36 items-end gap-[2px] border-b border-border"
          onMouseLeave={() => setHovered(null)}
          data-testid="volume-bars"
        >
          {days.map((day, index) => (
            <div
              key={day.date}
              className="group flex h-full min-w-0 flex-1 items-end"
              onMouseEnter={() => setHovered(index)}
            >
              <div
                className={`mx-auto w-full max-w-10 rounded-t-[4px] bg-chart-1 transition-opacity ${
                  hovered !== null && hovered !== index ? "opacity-50" : ""
                }`}
                style={{ height: `${(day.uploaded / max) * 100}%` }}
              />
            </div>
          ))}
        </div>
        <div className="mt-1 ml-8 flex justify-between text-xs text-muted-foreground">
          <span>{days[0] ? dayLabel(days[0].date) : ""}</span>
          <span>{days.length > 1 ? dayLabel(days[days.length - 1]!.date) : ""}</span>
        </div>
      </div>
      <table className="sr-only">
        <caption>Documents uploaded per day</caption>
        <thead>
          <tr>
            <th scope="col">Day</th>
            <th scope="col">Uploaded</th>
          </tr>
        </thead>
        <tbody>
          {days.map((day) => (
            <tr key={day.date}>
              <th scope="row">{dayLabel(day.date)}</th>
              <td>{day.uploaded}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
