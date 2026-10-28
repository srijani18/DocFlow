import { CheckIcon } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";

import { InlineMark, Wordmark } from "@/components/brand";
import { ThemeSwitch } from "@/components/theme-switch";

import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Sign in · DocFlow" };

const POINTS = [
  "Invoices, receipts and purchase orders",
  "Fields extracted with a confidence score",
  "Your own private workspace",
];

export default function LoginPage() {
  return (
    <main className="grid flex-1 bg-background lg:grid-cols-2">
      <section className="bg-brand-gradient relative hidden flex-col justify-between overflow-hidden p-12 text-white lg:flex">
        <div className="rounded-xl bg-card/95 p-2 pr-4 text-foreground shadow-lg w-fit">
          <Wordmark />
        </div>
        <div>
          <h1 className="text-5xl leading-tight font-semibold tracking-tight">
            Paperwork in,
            <br />
            clean data out.
          </h1>
          <ul className="mt-8 flex flex-col gap-3 text-white/90">
            {POINTS.map((point) => (
              <li key={point} className="flex items-center gap-3">
                <span className="inline-flex size-6 items-center justify-center rounded-full bg-white/20">
                  <CheckIcon className="size-3.5" aria-hidden />
                </span>
                {point}
              </li>
            ))}
          </ul>
        </div>
        <p className="text-sm text-white/70">Please upload only sample or synthetic documents.</p>
        <div className="pointer-events-none absolute -right-24 -bottom-24 size-96 rounded-full bg-white/10 blur-3xl" />
      </section>
      <section className="relative flex flex-col items-center justify-center gap-8 px-6 py-16">
        <ThemeSwitch className="absolute top-4 right-4" />
        <div className="lg:hidden">
          <Wordmark />
        </div>
        <div className="w-full max-w-sm">
          <h2 className="mb-6 text-center text-3xl font-semibold tracking-tight">
            Welcome to <InlineMark />
            <span className="text-brand-gradient">DocFlow</span>
          </h2>
          {/* The form reads ?next= from the URL, which is only known at request time. */}
          <Suspense>
            <LoginForm />
          </Suspense>
        </div>
      </section>
    </main>
  );
}
