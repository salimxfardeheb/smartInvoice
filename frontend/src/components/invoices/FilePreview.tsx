"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api-client";
import { ApiError } from "@/lib/errors";
import type { Invoice } from "@/types";
import { Alert } from "@/components/ui/Alert";
import { Spinner } from "@/components/ui/Spinner";

interface PreviewState {
  url: string | null;
  contentType: string | null;
  loading: boolean;
  error: string | null;
}

/** Aperçu du fichier source (image ou PDF) chargé avec authentification. */
export function FilePreview({ invoice }: { invoice: Invoice }) {
  const [state, setState] = useState<PreviewState>({
    url: null,
    contentType: null,
    loading: true,
    error: null,
  });

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    setState({ url: null, contentType: null, loading: true, error: null });

    api
      .fetchFile(invoice.id)
      .then(({ blob, contentType }) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setState({ url: objectUrl, contentType, loading: false, error: null });
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        const message = cause instanceof ApiError ? cause.detail : "Impossible de charger le fichier.";
        setState({ url: null, contentType: null, loading: false, error: message });
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [invoice.id]);

  if (state.loading) return <Spinner label="Chargement du fichier…" />;

  if (state.error) {
    return <Alert tone="danger">{state.error}</Alert>;
  }

  const isImage = (state.contentType ?? invoice.file_info?.content_type ?? "").startsWith("image/");
  const isPdf = (state.contentType ?? invoice.file_info?.content_type ?? "") === "application/pdf";

  return (
    <div>
      {isImage && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={state.url ?? ""}
          alt={`Aperçu du document ${invoice.invoice_number}`}
          className="max-h-[28rem] w-full rounded-md border border-slate-200 object-contain bg-white"
        />
      )}
      {isPdf && (
        <iframe
          src={state.url ?? ""}
          title={`Aperçu du document ${invoice.invoice_number}`}
          className="h-[28rem] w-full rounded-md border border-slate-200 bg-white"
        />
      )}
      {!isImage && !isPdf && (
        <Alert tone="info">
          Aperçu non disponible pour ce type de fichier (
          {state.contentType ?? "inconnu"}).
        </Alert>
      )}
      {state.url && (
        <a
          href={state.url}
          download={invoice.file_info?.original_filename ?? `facture-${invoice.id}`}
          className="mt-3 inline-block text-xs font-medium text-brand-600 hover:underline"
        >
          Télécharger {invoice.file_info?.original_filename ?? "le fichier"}
        </a>
      )}
    </div>
  );
}
