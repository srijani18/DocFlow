"use client";

import { Button } from "@/components/ui/button";

export type ReviewProblem = {
  id: string;
  path: string;
  message: string;
  tone: "error" | "warning" | "info" | "confidence";
};

const TONE = {
  error: "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300",
  warning: "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  info: "bg-muted text-muted-foreground",
  confidence: "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
} as const;

const TONE_LABEL = {
  error: "Error",
  warning: "Warning",
  info: "Info",
  confidence: "Unsure",
} as const;

/** Open problems, and a button that moves focus to the next one (F7 AC2). */
export function ProblemList({
  problems,
  onGoTo,
  onNext,
}: {
  problems: ReviewProblem[];
  onGoTo: (problem: ReviewProblem) => void;
  onNext: () => void;
}) {
  if (problems.length === 0) {
    return <p className="text-sm text-muted-foreground">No open problems.</p>;
  }
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-medium">
          {problems.length} thing{problems.length === 1 ? "" : "s"} to check
        </h3>
        <Button variant="outline" size="sm" onClick={onNext}>
          Next problem
        </Button>
      </div>
      <ul className="flex max-h-48 flex-col gap-1 overflow-y-auto">
        {problems.map((problem) => (
          <li key={problem.id}>
            <button
              type="button"
              onClick={() => onGoTo(problem)}
              className="flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-muted"
            >
              <span
                className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${TONE[problem.tone]}`}
              >
                {TONE_LABEL[problem.tone]}
              </span>
              <span className="min-w-0">{problem.message}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
