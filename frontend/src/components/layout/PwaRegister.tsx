"use client";

import { useEffect } from "react";

/** Enregistre le service worker en production (cache offline des lectures). */
export function PwaRegister() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") return;
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // Le SW est un bonus ; on ne bloque pas l'application en cas d'échec.
    });
  }, []);
  return null;
}