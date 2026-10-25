import { ScanTextIcon } from "lucide-react";
import Link from "next/link";

const MARK_SIZES = {
  sm: "size-8 rounded-lg [&_svg]:size-4",
  md: "size-10 rounded-xl [&_svg]:size-5",
  lg: "size-12 rounded-2xl [&_svg]:size-6",
} as const;

/** The DocFlow mark: a scan icon on the brand gradient. */
export function LogoMark({ size = "md" }: { size?: keyof typeof MARK_SIZES }) {
  return (
    <span
      className={`bg-brand-gradient inline-flex shrink-0 items-center justify-center text-white shadow-sm shadow-primary/30 ${MARK_SIZES[size]}`}
      aria-hidden
    >
      <ScanTextIcon />
    </span>
  );
}

export function Wordmark({ href = "/", size = "md" }: { href?: string; size?: "sm" | "md" }) {
  return (
    <Link href={href} className="inline-flex items-center gap-2.5" aria-label="DocFlow home">
      <LogoMark size={size} />
      <span className={`font-semibold tracking-tight ${size === "sm" ? "text-base" : "text-lg"}`}>
        DocFlow
      </span>
    </Link>
  );
}

/** The outlined mark that sits inside headlines ("Why [mark] DocFlow"). */
export function InlineMark() {
  return (
    <span
      className="mx-1 inline-flex size-[0.95em] translate-y-[0.08em] items-center justify-center rounded-[0.22em] border-2 border-primary/30 bg-white/70 align-baseline text-primary"
      aria-hidden
    >
      <ScanTextIcon className="size-[0.55em]" strokeWidth={2.4} />
    </span>
  );
}
