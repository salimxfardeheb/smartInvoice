"use client";

/** Barre latérale de navigation + contenu principal. */

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { useAuth } from "@/lib/auth";
import { ROLE_LABELS } from "@/lib/status";

const NAV_ITEMS = [
  { href: "/", label: "Tableau de bord", icon: "▦" },
  { href: "/invoices", label: "Factures", icon: "≡" },
  { href: "/invoices/upload", label: "Déposer une facture", icon: "+" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);

  async function handleLogout() {
    await logout();
    router.replace("/login");
  }

  return (
    <div className="min-h-screen">
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex flex-col bg-slate-900 text-slate-200 transition-all ${
          collapsed ? "w-16" : "w-60"
        }`}
      >
        <div className="flex h-14 items-center gap-2 px-4">
          <span className="text-xl" aria-hidden>
            🧾
          </span>
          {!collapsed && (
            <span className="text-sm font-semibold text-white">SmartInvoice</span>
          )}
        </div>
        <nav className="mt-2 flex-1 space-y-1 px-2">
          {NAV_ITEMS.map((item) => {
            const isActive =
              item.href === "/"
                ? pathname === "/"
                : pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={isActive ? "page" : undefined}
                className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm transition ${
                  isActive
                    ? "bg-brand-600 text-white"
                    : "text-slate-300 hover:bg-slate-800 hover:text-white"
                }`}
              >
                <span aria-hidden className="w-4 text-center">
                  {item.icon}
                </span>
                {!collapsed && item.label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-slate-700 p-3">
          {user && (
            <div className="mb-2 px-1">
              {!collapsed && (
                <>
                  <p className="truncate text-sm font-medium text-white">
                    {user.full_name ?? user.username}
                  </p>
                  <p className="text-xs text-slate-400">{ROLE_LABELS[user.role] ?? user.role}</p>
                </>
              )}
            </div>
          )}
          <button
            type="button"
            onClick={handleLogout}
            className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm text-slate-300 hover:bg-slate-800 hover:text-white"
          >
            <span aria-hidden className="w-4 text-center">
              ⏻
            </span>
            {!collapsed && "Déconnexion"}
          </button>
        </div>
      </aside>
      <div className={`transition-all ${collapsed ? "pl-16" : "pl-60"}`}>
        <header className="flex h-14 items-center justify-between border-b border-slate-200 bg-white px-6">
          <button
            type="button"
            onClick={() => setCollapsed((value) => !value)}
            aria-label={collapsed ? "Étendre la barre" : "Réduire la barre"}
            className="rounded-md p-2 text-slate-500 hover:bg-slate-100"
          >
            {collapsed ? "›" : "‹"}
          </button>
          <span className="text-sm text-slate-500">Interface de gestion des factures</span>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
      </div>
    </div>
  );
}
