"use client";

import type { ReactNode } from "react";

/** Badge générique coloré par `tone`. */
export function Badge({
  children,
  tone = "slate",
  className = "",
}: {
  children: ReactNode;
  tone?: string;
  className?: string;
}) {
  const tones: Record<string, string> = {
    slate: "bg-slate-100 text-slate-700 ring-slate-300",
    blue: "bg-blue-50 text-blue-700 ring-blue-300",
    amber: "bg-amber-50 text-amber-700 ring-amber-300",
    emerald: "bg-emerald-50 text-emerald-700 ring-emerald-300",
    teal: "bg-teal-50 text-teal-700 ring-teal-300",
    rose: "bg-rose-50 text-rose-700 ring-rose-300",
    red: "bg-red-50 text-red-700 ring-red-300",
    sky: "bg-sky-50 text-sky-700 ring-sky-300",
  };
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${tones[tone] ?? tones.slate} ${className}`}
    >
      {children}
    </span>
  );
}
