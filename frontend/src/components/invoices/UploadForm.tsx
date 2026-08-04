"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api-client";
import type { Invoice, SupplierBrief } from "@/types";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";

const ACCEPTED_TYPES = ["application/pdf", "image/jpeg", "image/png"];
const ACCEPTED_EXTENSIONS = [".pdf", ".jpg", ".jpeg", ".png"];
const MAX_SIZE_BYTES = 20 * 1024 * 1024;

/** Valide le fichier côté client (type + taille) et renvoie une erreur. */
export function validateFile(file: File | null): string | null {
  if (!file) return "Sélectionnez un document.";
  const extension = `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`;
  const typeOk = ACCEPTED_TYPES.includes(file.type);
  const extOk = ACCEPTED_EXTENSIONS.includes(extension);
  if (!typeOk && !extOk) {
    return "Format non pris en charge : PDF, JPG, JPEG ou PNG uniquement.";
  }
  if (file.size > MAX_SIZE_BYTES) {
    return "Fichier trop volumineux (20 Mo maximum).";
  }
  if (file.size === 0) {
    return "Le fichier est vide.";
  }
  return null;
}

/** Formulaire de dépôt d'une facture (upload + métadonnées). */
export function UploadForm({
  onSuccess,
  suppliers,
}: {
  onSuccess?: (invoice: Invoice) => void;
  suppliers?: SupplierBrief[];
}) {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [invoiceNumber, setInvoiceNumber] = useState("");
  const [supplierId, setSupplierId] = useState<string>("");
  const [issueDate, setIssueDate] = useState("");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const objectUrlRef = useRef<string | null>(null);

  const supplierOptions = useMemo(
    () =>
      (suppliers ?? []).map((supplier) => ({
        value: String(supplier.id),
        label: `${supplier.name} (id ${supplier.id})`,
      })),
    [suppliers],
  );

  const canSubmit =
    !busy && Boolean(file) && invoiceNumber.trim().length > 0 && supplierId !== "" && !fileError;

  function handleFileChange(selected: File | null) {
    setError(null);
    setFileError(validateFile(selected));
    setFile(selected);
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    setPreviewUrl(null);
    if (selected && !validateFile(selected)) {
      objectUrlRef.current = URL.createObjectURL(selected);
      setPreviewUrl(objectUrlRef.current);
    }
  }

  useEffect(
    () => () => {
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    },
    [],
  );

  const isImagePreview = Boolean(previewUrl && file?.type.startsWith("image/"));
  const isPdfPreview = Boolean(previewUrl && file?.type === "application/pdf");

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!file || !invoiceNumber.trim() || !supplierId) return;
    const validation = validateFile(file);
    if (validation) {
      setFileError(validation);
      return;
    }
    setBusy(true);
    setError(null);
    setProgress(0);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("invoice_number", invoiceNumber.trim());
      formData.append("supplier_id", supplierId);
      if (issueDate) formData.append("issue_date", issueDate);
      const invoice = await api.depositInvoice(formData, setProgress);
      if (onSuccess) {
        onSuccess(invoice);
      } else {
        router.push(`/invoices/${invoice.id}/ocr`);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Échec du dépôt de la facture.");
      setProgress(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader title="Déposer une facture" subtitle="Formats acceptés : PDF, JPG, JPEG, PNG (20 Mo max)" />
      <CardBody>
        {error && (
          <Alert tone="danger" className="mb-4" title="Dépôt refusé">
            {error}
          </Alert>
        )}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="file-input" className="mb-1 block text-xs font-medium text-slate-700">
              Document *
            </label>
            <input
              id="file-input"
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
              onChange={(event) => handleFileChange(event.target.files?.[0] ?? null)}
              aria-describedby={fileError ? "file-error" : undefined}
              className="block w-full cursor-pointer rounded-md border border-slate-300 bg-white text-sm text-slate-700 file:mr-3 file:rounded-md file:border-0 file:bg-brand-50 file:px-3 file:py-2 file:text-sm file:font-medium file:text-brand-700 hover:file:bg-brand-100"
            />
            {fileError && (
              <p id="file-error" role="alert" className="mt-1 text-xs text-rose-600">
                {fileError}
              </p>
            )}
            {file && !fileError && (
              <p className="mt-1 text-xs text-slate-500">
                {file.name} · {(file.size / 1024).toFixed(1)} Ko
              </p>
            )}
            {previewUrl && (isImagePreview || isPdfPreview) && (
              <div className="mt-3 overflow-hidden rounded-md border border-slate-200">
                <p className="bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-500">
                  Aperçu de {file?.name}
                </p>
                {isImagePreview ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={previewUrl}
                    alt={`Aperçu du document ${file?.name ?? ""}`}
                    className="max-h-72 w-full object-contain bg-white"
                  />
                ) : (
                  <iframe
                    src={previewUrl}
                    title={`Aperçu du document ${file?.name ?? ""}`}
                    className="h-72 w-full bg-white"
                  />
                )}
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              label="Numéro de facture *"
              value={invoiceNumber}
              onChange={(event) => setInvoiceNumber(event.target.value)}
              placeholder="Ex. : FAC-2026-0142"
              maxLength={100}
            />
            <Select
              label="Fournisseur *"
              value={supplierId}
              onChange={(event) => setSupplierId(event.target.value)}
              options={[
                { value: "", label: "Sélectionner un fournisseur…" },
                ...supplierOptions,
              ]}
            />
            <Input
              label="Date d'émission"
              type="date"
              value={issueDate}
              onChange={(event) => setIssueDate(event.target.value)}
            />
          </div>

          {busy && progress !== null && (
            <div
              role="progressbar"
              aria-label="Envoi du document"
              aria-valuenow={progress}
              aria-valuemin={0}
              aria-valuemax={100}
              className="space-y-1"
            >
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
                <div
                  className="h-full rounded-full bg-brand-600 transition-all"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <p className="text-xs text-slate-500">Envoi : {progress} %</p>
            </div>
          )}

          <div className="flex justify-end">
            <Button type="submit" disabled={!canSubmit} loading={busy}>
              Déposer la facture
            </Button>
          </div>
        </form>
      </CardBody>
    </Card>
  );
}

/** Hook : récupère les fournisseurs connus depuis la liste des factures. */
export function useKnownSuppliers(): {
  suppliers: SupplierBrief[];
  loading: boolean;
} {
  const [suppliers, setSuppliers] = useState<SupplierBrief[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api
      .listInvoices({}, 200, 0)
      .then((response) => {
        if (cancelled) return;
        const unique = new Map<number, SupplierBrief>();
        for (const invoice of response.items) {
          unique.set(invoice.supplier.id, invoice.supplier);
        }
        setSuppliers([...unique.values()].sort((a, b) => a.name.localeCompare(b.name)));
      })
      .catch(() => {
        if (!cancelled) setSuppliers([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { suppliers, loading };
}