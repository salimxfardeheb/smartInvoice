"use client";

import type { ReactNode } from "react";

import { BADGE_BASE, BADGE_TONES } from "@/lib/design";

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
  return (
    <span
      className={`${BADGE_BASE} ${BADGE_TONES[tone] ?? BADGE_TONES.slate} ${className}`}
    >
      {children}
    </span>
  );
}