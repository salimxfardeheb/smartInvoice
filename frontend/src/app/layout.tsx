import type { Metadata } from "next";

import { AuthProvider } from "@/lib/auth";
import { PwaRegister } from "@/components/layout/PwaRegister";
import "./globals.css";

export const metadata: Metadata = {
  title: "SmartInvoice",
  description:
    "Gestion des factures fournisseurs : OCR, matching et validation comptable.",
  manifest: "/manifest.webmanifest",
  icons: {
    icon: "/icons/icon.svg",
  },
};

export const viewport = {
  themeColor: "#2563eb",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fr">
      <body>
        <AuthProvider>{children}</AuthProvider>
        <PwaRegister />
      </body>
    </html>
  );
}
