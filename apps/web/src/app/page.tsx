import {
  ArrowRightIcon,
  BadgeCheckIcon,
  CloudUploadIcon,
  ListChecksIcon,
  ScanSearchIcon,
  ShieldCheckIcon,
  SparklesIcon,
  WorkflowIcon,
} from "lucide-react";
import Link from "next/link";

import { ThemeSwitch } from "@/components/theme-switch";

import { ApiStatus } from "@/components/api-status";
import { InlineMark, Wordmark } from "@/components/brand";
import { AppPreview } from "@/components/landing/app-preview";
import { buttonVariants } from "@/components/ui/button";

const ADVANTAGES = [
  {
    icon: ScanSearchIcon,
    title: "Reads any layout",
    body: "PDFs, scans and phone photos. A vision model reads the page itself, so there are no templates to set up per vendor.",
  },
  {
    icon: SparklesIcon,
    title: "Shows its confidence",
    body: "Every field comes with a confidence score. Uncertain values are highlighted, so people check only what needs checking.",
    featured: true,
  },
  {
    icon: BadgeCheckIcon,
    title: "Built for GST",
    body: "GSTINs, HSN/SAC codes, CGST, SGST and IGST lines are first-class fields, validated against the official formats.",
  },
];

const STEPS = [
  {
    icon: CloudUploadIcon,
    title: "Upload",
    body: "Drop invoices, receipts or purchase orders. Duplicates are caught automatically.",
  },
  {
    icon: WorkflowIcon,
    title: "Classify",
    body: "DocFlow works out what each document is, in a few seconds.",
  },
  {
    icon: ScanSearchIcon,
    title: "Extract",
    body: "Vendor, dates, line items, taxes and totals, checked against a schema.",
  },
  {
    icon: ListChecksIcon,
    title: "Review",
    body: "Low-confidence fields are flagged for a quick human check.",
  },
];

export default function Home() {
  return (
    <main className="flex flex-1 flex-col bg-background">
      {/* Hero */}
      <section className="px-3 pt-3 sm:px-4 sm:pt-4">
        <div className="bg-hero-glow relative overflow-hidden rounded-[2rem] px-5 pb-0 sm:rounded-[2.5rem] sm:px-10">
          <header className="mx-auto flex max-w-6xl items-center justify-between py-5">
            <Wordmark />
            <nav className="flex items-center gap-2 sm:gap-6">
              <ThemeSwitch className="hidden sm:inline-flex" />
              <Link
                href="/login"
                className="text-sm font-medium text-foreground/80 hover:text-foreground"
              >
                Sign in
              </Link>
              <Link
                href="/login"
                className={`${buttonVariants({ variant: "dark" })} sm:h-11 sm:px-6`}
              >
                Get started
              </Link>
            </nav>
          </header>

          <div className="mx-auto max-w-4xl pt-10 text-center sm:pt-16">
            <h1 className="text-[2.6rem] leading-[1.05] font-semibold tracking-tight sm:text-7xl">
              Let <InlineMark />
              <span className="text-brand-gradient">DocFlow</span>
              <br />
              read your invoices
            </h1>
            <p className="mx-auto mt-6 max-w-xl text-base text-foreground/75 sm:text-lg">
              Upload invoices, receipts and purchase orders. DocFlow classifies them, extracts every
              field with AI and flags what needs a human check.
            </p>
            <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row sm:gap-4">
              <Link href="/login" className={`${buttonVariants({ size: "lg" })} min-w-44`}>
                Get started
              </Link>
              <a
                href="#why"
                className={`${buttonVariants({ variant: "outline", size: "lg" })} min-w-44`}
              >
                Learn more
              </a>
            </div>
          </div>

          <div className="mx-auto mt-14 max-w-5xl translate-y-6 sm:mt-16">
            <AppPreview />
          </div>
        </div>
      </section>

      {/* Why DocFlow */}
      <section
        id="why"
        className="mx-auto grid w-full max-w-6xl gap-10 px-5 py-24 sm:px-10 lg:grid-cols-[14rem_1fr]"
      >
        <div className="flex flex-col gap-6">
          <span className="w-fit rounded-full border px-4 py-1.5 text-xs font-semibold tracking-[0.18em]">
            ADVANTAGES
          </span>
          <p className="hidden text-sm text-muted-foreground lg:block">
            Built as an open, measurable system: every AI call is logged with its cost and latency.
          </p>
        </div>
        <div>
          <h2 className="text-4xl font-semibold tracking-tight sm:text-5xl">
            Why <InlineMark />
            <span className="text-brand-gradient">DocFlow</span>
          </h2>
          <p className="mt-5 max-w-2xl text-lg text-foreground/75">
            Typing data in from invoices is slow, error-prone and expensive. DocFlow turns documents
            into clean, structured data in seconds, and keeps a person in the loop where it matters.
          </p>
          <div className="mt-10 grid gap-5 md:grid-cols-3">
            {ADVANTAGES.map(({ icon: Icon, title, body, featured }) => (
              <article
                key={title}
                className={`flex flex-col gap-6 rounded-3xl p-6 ${
                  featured
                    ? "bg-brand-gradient text-white shadow-xl shadow-primary/25"
                    : "border bg-card"
                }`}
              >
                <div className="flex items-center gap-3">
                  <span
                    className={`inline-flex size-11 items-center justify-center rounded-xl ${
                      featured ? "bg-white text-indigo-600" : "bg-muted text-foreground"
                    }`}
                  >
                    <Icon className="size-5" />
                  </span>
                  <h3 className="text-xl font-semibold tracking-tight">{title}</h3>
                </div>
                <p className={featured ? "text-white/90" : "text-foreground/70"}>{body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="px-3 sm:px-4">
        <div className="rounded-[2rem] bg-surface px-5 py-20 sm:rounded-[2.5rem] sm:px-10">
          <div className="mx-auto max-w-6xl">
            <h2 className="text-center text-4xl font-semibold tracking-tight sm:text-5xl">
              From upload to <span className="text-brand-gradient">clean data</span>
            </h2>
            <ol className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              {STEPS.map(({ icon: Icon, title, body }, index) => (
                <li key={title} className="flex flex-col gap-4 rounded-3xl bg-card p-6 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="inline-flex size-11 items-center justify-center rounded-xl bg-accent text-primary">
                      <Icon className="size-5" />
                    </span>
                    <span className="text-sm font-semibold text-muted-foreground">
                      0{index + 1}
                    </span>
                  </div>
                  <h3 className="text-lg font-semibold">{title}</h3>
                  <p className="text-sm text-foreground/70">{body}</p>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </section>

      {/* Call to action */}
      <section className="mx-auto w-full max-w-6xl px-5 py-24 sm:px-10">
        <div className="bg-brand-gradient flex flex-col items-start justify-between gap-6 rounded-[2rem] p-8 text-white shadow-xl shadow-primary/25 sm:flex-row sm:items-center sm:p-12">
          <div>
            <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
              Try it with a sample invoice
            </h2>
            <p className="mt-2 flex items-center gap-2 text-white/85">
              <ShieldCheckIcon className="size-4" /> Free to use. Please upload only sample or
              synthetic documents.
            </p>
          </div>
          <Link
            href="/login"
            className={`${buttonVariants({ variant: "subtle", size: "lg" })} text-foreground`}
          >
            Get started <ArrowRightIcon />
          </Link>
        </div>
      </section>

      <footer className="mx-auto flex w-full max-w-6xl flex-col items-start justify-between gap-3 border-t px-5 py-8 text-sm text-muted-foreground sm:flex-row sm:items-center sm:px-10">
        <Wordmark size="sm" />
        <ApiStatus />
      </footer>
    </main>
  );
}
