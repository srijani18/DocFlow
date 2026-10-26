"use client";

import { FileTextIcon, LayoutGridIcon, SettingsIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/app", label: "Dashboard", icon: LayoutGridIcon, exact: true },
  { href: "/app/documents", label: "Documents", icon: FileTextIcon, exact: false },
  { href: "/app/settings", label: "Settings", icon: SettingsIcon, exact: false },
];

type Orientation = "vertical" | "horizontal";

function isActive(pathname: string, href: string, exact: boolean) {
  return exact ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
}

/** The links themselves. With no pathname (while it streams in) nothing is highlighted. */
export function NavLinks({
  pathname,
  orientation = "vertical",
}: {
  pathname: string | null;
  orientation?: Orientation;
}) {
  return (
    <nav
      aria-label="Main"
      className={orientation === "vertical" ? "flex flex-col gap-1" : "flex items-center gap-1"}
    >
      {ITEMS.map(({ href, label, icon: Icon, exact }) => {
        const active = pathname !== null && isActive(pathname, href, exact);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-colors ${
              active
                ? "bg-accent font-semibold text-accent-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground"
            }`}
          >
            <Icon className="size-4" aria-hidden />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

/** Main navigation with the current page highlighted. The URL is request-time data, so
 * render it inside <Suspense> with <NavLinks pathname={null}> as the fallback. */
export function AppNav({ orientation = "vertical" }: { orientation?: Orientation }) {
  return <NavLinks pathname={usePathname()} orientation={orientation} />;
}
