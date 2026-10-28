"use client";

import { MonitorIcon, MoonIcon, SunIcon } from "lucide-react";
import { useSyncExternalStore } from "react";

import { chooseTheme, readChoice, subscribeToTheme, type ThemeChoice } from "@/lib/theme";

const OPTIONS: { value: ThemeChoice; label: string; icon: typeof SunIcon }[] = [
  { value: "light", label: "Light", icon: SunIcon },
  { value: "dark", label: "Dark", icon: MoonIcon },
  { value: "system", label: "System", icon: MonitorIcon },
];

/** Light / Dark / System (F17 AC2). The server doesn't know the choice, so it renders
 * "System" selected and the browser corrects it after hydration. */
export function ThemeSwitch({ className = "" }: { className?: string }) {
  const choice = useSyncExternalStore(subscribeToTheme, readChoice, () => "system" as const);
  return (
    <div
      role="group"
      aria-label="Theme"
      className={`inline-flex items-center gap-0.5 rounded-full border bg-card p-0.5 ${className}`}
    >
      {OPTIONS.map(({ value, label, icon: Icon }) => (
        <button
          key={value}
          type="button"
          aria-label={label}
          aria-pressed={choice === value}
          title={label}
          onClick={() => chooseTheme(value)}
          className={`inline-flex size-7 items-center justify-center rounded-full transition-colors ${
            choice === value
              ? "bg-accent text-accent-foreground"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <Icon className="size-3.5" aria-hidden />
        </button>
      ))}
    </div>
  );
}
