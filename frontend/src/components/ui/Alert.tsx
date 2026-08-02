"use client";

import type { ReactNode } from "react";

type Tone = "info" | "success" | "warning" | "danger";

const TONES: Record<Tone, string> = {
  info: "border-blue-200 bg-blue-50 text-blue-800",
  success: "border-emerald-200 bg-emerald-50 text-emerald-800",
  warning: "border-amber-200 bg-amber-50 text-amber-800",
  danger: "border-rose-200 bg-rose-50 text-rose-800",
};

export function Alert({
  tone = "info",
  title,
  children,
  className = "",
}: {
  tone?: Tone;
  title?: string;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={`rounded-md border px-4 py-3 text-sm ${TONES[tone]} ${className}`}
    >
      {title && <p className="font-medium">{title}</p>}
      {children && <div className="mt-0.5">{children}</div>}
    </div>
  );
}
