"use client";

/**
 * Logo SmartInvoice servi depuis `public/icons`.
 *
 * Deux formes (`mark` : la marque seule, `lockup` : marque + nom) et deux
 * tons (`color` sur fond clair, `white` sur fond sombre). La largeur est
 * déduite de la hauteur demandée pour préserver les proportions du fichier.
 */

import Image from "next/image";

type LogoVariant = "mark" | "lockup";
type LogoTone = "color" | "white";

const ASSETS: Record<LogoVariant, { ratio: number; src: Record<LogoTone, string> }> = {
  mark: {
    ratio: 376 / 514,
    src: {
      color: "/icons/smartinvoice-icone.png",
      white: "/icons/smartinvoice-icone-blanc-transparent.png",
    },
  },
  lockup: {
    ratio: 1385 / 246,
    src: {
      color: "/icons/smartinvoice-lockup-trim.png",
      white: "/icons/smartinvoice-lockup-blanc-transparent.png",
    },
  },
};

export function Logo({
  variant = "lockup",
  tone = "color",
  height = 32,
  priority = false,
  className = "",
}: {
  variant?: LogoVariant;
  tone?: LogoTone;
  /** Hauteur de rendu en pixels ; la largeur suit le ratio du fichier. */
  height?: number;
  priority?: boolean;
  className?: string;
}) {
  const asset = ASSETS[variant];
  return (
    <Image
      src={asset.src[tone]}
      alt="SmartInvoice"
      width={Math.round(height * asset.ratio)}
      height={height}
      priority={priority}
      // L'image Docker (build `standalone`) n'embarque pas `sharp` : l'optimiseur
      // Next.js échouerait à l'exécution. Les PNG sont déjà aux bonnes tailles.
      unoptimized
      className={className}
    />
  );
}
