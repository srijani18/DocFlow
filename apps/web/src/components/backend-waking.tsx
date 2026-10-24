import { CloudOffIcon, LoaderCircleIcon, TriangleAlertIcon } from "lucide-react";

import { Button } from "@/components/ui/button";

/** Shown while a request retries because the API is waking from sleep (spec AC20). */
export function BackendWaking() {
  return (
    <div role="status" className="flex items-start gap-3 rounded-lg border p-4 text-sm">
      <LoaderCircleIcon className="mt-0.5 animate-spin text-muted-foreground" aria-hidden />
      <div>
        <p className="font-medium">Starting up the server…</p>
        <p className="text-muted-foreground">
          DocFlow runs on a free tier that sleeps when idle. Waking up can take up to a minute.
        </p>
      </div>
    </div>
  );
}

const COPY = {
  unreachable: {
    Icon: CloudOffIcon,
    title: "Couldn't reach the DocFlow server.",
    detail: "It may still be starting up, or your connection may be down.",
  },
  error: {
    Icon: TriangleAlertIcon,
    title: "Something went wrong loading your account.",
    detail: "Try again in a moment.",
  },
} as const;

/** Shown when the retries have run out, or for an error retrying won't fix. */
export function BackendUnavailable({
  reason,
  onRetry,
}: {
  reason: keyof typeof COPY;
  onRetry: () => void;
}) {
  const { Icon, title, detail } = COPY[reason];
  return (
    <div role="alert" className="flex items-start gap-3 rounded-lg border p-4 text-sm">
      <Icon className="mt-0.5 text-destructive" aria-hidden />
      <div className="flex flex-col items-start gap-2">
        <div>
          <p className="font-medium">{title}</p>
          <p className="text-muted-foreground">{detail}</p>
        </div>
        <Button variant="outline" size="sm" onClick={onRetry}>
          Try again
        </Button>
      </div>
    </div>
  );
}
