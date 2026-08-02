"use client";

import type { ReactNode } from "react";

/** Tableau simple, stylisé de façon cohérente. */
export function Table({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`overflow-x-auto ${className}`}>
      <table className="min-w-full divide-y divide-slate-200 text-sm">{children}</table>
    </div>
  );
}

export function THead({ children }: { children: ReactNode }) {
  return (
    <thead className="bg-slate-50">
      <tr>{children}</tr>
    </thead>
  );
}

export function TH({ children, className = "" }: { children?: ReactNode; className?: string }) {
  return (
    <th
      scope="col"
      className={`px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500 ${className}`}
    >
      {children}
    </th>
  );
}

export function TR({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <tr className={`border-b border-slate-100 last:border-0 hover:bg-slate-50/70 ${className}`}>
      {children}
    </tr>
  );
}

export function TD({ children, className = "" }: { children?: ReactNode; className?: string }) {
  return <td className={`whitespace-nowrap px-4 py-3 text-slate-700 ${className}`}>{children}</td>;
}
