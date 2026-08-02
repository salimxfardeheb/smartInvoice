"use client";

/** Spinner de chargement centré. */
export function Spinner({ label = "Chargement…" }: { label?: string }) {
  return (
    <div
      role="status"
      className="flex flex-col items-center justify-center gap-3 py-12 text-slate-500"
    >
      <span
        aria-hidden
        className="h-8 w-8 animate-spin rounded-full border-2 border-slate-300 border-t-brand-600"
      />
      <span className="text-sm">{label}</span>
    </div>
  );
}
