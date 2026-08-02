"use client";

import { useEffect, useState } from "react";

import type {
  Invoice,
  InvoiceCorrectionPayload,
  InvoiceLine,
} from "@/types";
import { useInvoiceActions } from "@/hooks/useInvoices";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Input, Textarea } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Table, TD, TH, THead, TR } from "@/components/ui/Table";

interface LineForm {
  line_number: number;
  description: string;
  product_ref: string;
  quantity: string;
  unit_price: string;
  tax_rate: string;
  discount: string;
  amount: string;
}

interface FormState {
  invoice_number: string;
  issue_date: string;
  due_date: string;
  currency: string;
  total_excl_tax: string;
  tax_amount: string;
  total_incl_tax: string;
  discount: string;
  shipping_fees: string;
  lines: LineForm[];
}

function toStringValue(value: string | number | null | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

function toFormState(invoice: Invoice): FormState {
  const toLine = (line: InvoiceLine): LineForm => ({
    line_number: line.line_number,
    description: line.description,
    product_ref: toStringValue(line.product_ref),
    quantity: toStringValue(line.quantity),
    unit_price: toStringValue(line.unit_price),
    tax_rate: toStringValue(line.tax_rate),
    discount: toStringValue(line.discount),
    amount: toStringValue(line.amount),
  });
  const lines = (invoice.extracted_data?.lines ?? []).map(toLine);
  if (lines.length === 0) {
    lines.push({ line_number: 1, description: "", product_ref: "", quantity: "", unit_price: "", tax_rate: "", discount: "", amount: "" });
  }
  return {
    invoice_number: invoice.invoice_number,
    issue_date: toStringValue(invoice.issue_date),
    due_date: toStringValue(invoice.due_date),
    currency: invoice.currency,
    total_excl_tax: toStringValue(invoice.total_excl_tax),
    tax_amount: toStringValue(invoice.tax_amount),
    total_incl_tax: toStringValue(invoice.total_incl_tax),
    discount: toStringValue(invoice.discount),
    shipping_fees: toStringValue(invoice.shipping_fees),
    lines,
  };
}

function buildCorrection(original: FormState, form: FormState): InvoiceCorrectionPayload {
  const payload: InvoiceCorrectionPayload = {};
  const scalarFields: Array<keyof Pick<FormState, "invoice_number" | "issue_date" | "due_date" | "currency" | "total_excl_tax" | "tax_amount" | "total_incl_tax" | "discount" | "shipping_fees">> =
    ["invoice_number", "issue_date", "due_date", "currency", "total_excl_tax", "tax_amount", "total_incl_tax", "discount", "shipping_fees"];

  for (const field of scalarFields) {
    const value = form[field];
    if (value !== original[field]) {
      (payload as Record<string, unknown>)[field] = value === "" ? null : value;
    }
  }

  if (JSON.stringify(form.lines) !== JSON.stringify(original.lines)) {
    payload.lines = form.lines.map((line) => ({
      line_number: line.line_number,
      description: line.description || "Ligne non décrite",
      product_ref: line.product_ref || null,
      quantity: line.quantity || null,
      unit_price: line.unit_price || null,
      tax_rate: line.tax_rate || null,
      discount: line.discount || null,
      amount: line.amount || null,
    }));
  }

  return payload;
}

/** Écran de validation : correction manuelle, validation, rejet, Vendor Bill. */
export function ValidationPanel({
  invoice,
  onUpdated,
}: {
  invoice: Invoice;
  onUpdated: (invoice: Invoice) => void;
}) {
  const [original, setOriginal] = useState<FormState>(() => toFormState(invoice));
  const [form, setForm] = useState<FormState>(() => toFormState(invoice));
  const [showReject, setShowReject] = useState(false);
  const [reason, setReason] = useState("");

  useEffect(() => {
    const next = toFormState(invoice);
    setOriginal(next);
    setForm(next);
    setReason("");
  }, [invoice]);

  const actions = useInvoiceActions(onUpdated);
  const canCorrect = invoice.status === "À vérifier";
  const canCreateBill = invoice.status === "Validée";

  const updateField = (field: keyof FormState, value: string) =>
    setForm((previous) => ({ ...previous, [field]: value }));

  const updateLine = (index: number, field: keyof LineForm, value: string) =>
    setForm((previous) => {
      const lines = previous.lines.map((line, i) => (i === index ? { ...line, [field]: value } : line));
      return { ...previous, lines };
    });

  async function handleSave() {
    const payload = buildCorrection(original, form);
    if (Object.keys(payload).length === 0) return;
    await actions.correct.run(invoice.id, payload);
  }

  return (
    <div className="space-y-4">
      {actions.correct.error && (
        <Alert tone="danger" title="Correction refusée">{actions.correct.error}</Alert>
      )}
      {actions.validate.error && (
        <Alert tone="danger" title="Validation refusée">{actions.validate.error}</Alert>
      )}
      {actions.reject.error && (
        <Alert tone="danger" title="Rejet refusé">{actions.reject.error}</Alert>
      )}
      {actions.createVendorBill.error && (
        <Alert tone="danger" title="Création Vendor Bill">{actions.createVendorBill.error}</Alert>
      )}

      {!canCorrect && invoice.status !== "Validée" && (
        <Alert tone="info">
          Les actions de validation sont disponibles uniquement pour une facture « À vérifier ».
        </Alert>
      )}

      <Card>
        <CardHeader title="Correction manuelle" subtitle="Champs de la facture extraits par OCR" />
        <CardBody>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Input label="Numéro de facture" value={form.invoice_number} disabled={!canCorrect}
              onChange={(event) => updateField("invoice_number", event.target.value)} />
            <Input label="Date d'émission" type="date" value={form.issue_date} disabled={!canCorrect}
              onChange={(event) => updateField("issue_date", event.target.value)} />
            <Input label="Date d'échéance" type="date" value={form.due_date} disabled={!canCorrect}
              onChange={(event) => updateField("due_date", event.target.value)} />
            <Input label="Devise" maxLength={3} value={form.currency} disabled={!canCorrect}
              onChange={(event) => updateField("currency", event.target.value.toUpperCase())} />
            <Input label="Total HT" value={form.total_excl_tax} disabled={!canCorrect}
              onChange={(event) => updateField("total_excl_tax", event.target.value)} />
            <Input label="TVA" value={form.tax_amount} disabled={!canCorrect}
              onChange={(event) => updateField("tax_amount", event.target.value)} />
            <Input label="Total TTC" value={form.total_incl_tax} disabled={!canCorrect}
              onChange={(event) => updateField("total_incl_tax", event.target.value)} />
            <Input label="Remise" value={form.discount} disabled={!canCorrect}
              onChange={(event) => updateField("discount", event.target.value)} />
            <Input label="Frais de port" value={form.shipping_fees} disabled={!canCorrect}
              onChange={(event) => updateField("shipping_fees", event.target.value)} />
          </div>

          <div className="mt-6">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Lignes</h3>
            <div className="overflow-x-auto rounded-md border border-slate-200">
              <Table>
                <THead>
                  <TH>N°</TH>
                  <TH>Description</TH>
                  <TH>Réf.</TH>
                  <TH>Qté</TH>
                  <TH>PU HT</TH>
                  <TH>TVA</TH>
                  <TH>Remise</TH>
                  <TH>Montant</TH>
                </THead>
                <tbody>
                  {form.lines.map((line, index) => (
                    <TR key={index}>
                      <TD>
                        <input
                          type="number"
                          min={1}
                          value={line.line_number}
                          disabled={!canCorrect}
                          aria-label={`Numéro de ligne ${index + 1}`}
                          onChange={(event) => updateLine(index, "line_number", event.target.value)}
                          className="w-16 rounded border border-slate-300 px-2 py-1 text-sm disabled:bg-slate-50"
                        />
                      </TD>
                      <TD>
                        <input
                          value={line.description}
                          disabled={!canCorrect}
                          aria-label={`Description de la ligne ${index + 1}`}
                          onChange={(event) => updateLine(index, "description", event.target.value)}
                          className="min-w-40 rounded border border-slate-300 px-2 py-1 text-sm disabled:bg-slate-50"
                        />
                      </TD>
                      <TD>
                        <input
                          value={line.product_ref}
                          disabled={!canCorrect}
                          aria-label={`Référence produit ligne ${index + 1}`}
                          onChange={(event) => updateLine(index, "product_ref", event.target.value)}
                          className="w-28 rounded border border-slate-300 px-2 py-1 text-sm disabled:bg-slate-50"
                        />
                      </TD>
                      <TD>
                        <input
                          value={line.quantity}
                          disabled={!canCorrect}
                          aria-label={`Quantité ligne ${index + 1}`}
                          onChange={(event) => updateLine(index, "quantity", event.target.value)}
                          className="w-20 rounded border border-slate-300 px-2 py-1 text-sm disabled:bg-slate-50"
                        />
                      </TD>
                      <TD>
                        <input
                          value={line.unit_price}
                          disabled={!canCorrect}
                          aria-label={`Prix unitaire ligne ${index + 1}`}
                          onChange={(event) => updateLine(index, "unit_price", event.target.value)}
                          className="w-24 rounded border border-slate-300 px-2 py-1 text-sm disabled:bg-slate-50"
                        />
                      </TD>
                      <TD>
                        <input
                          value={line.tax_rate}
                          disabled={!canCorrect}
                          aria-label={`Taux TVA ligne ${index + 1}`}
                          onChange={(event) => updateLine(index, "tax_rate", event.target.value)}
                          className="w-20 rounded border border-slate-300 px-2 py-1 text-sm disabled:bg-slate-50"
                        />
                      </TD>
                      <TD>
                        <input
                          value={line.discount}
                          disabled={!canCorrect}
                          aria-label={`Remise ligne ${index + 1}`}
                          onChange={(event) => updateLine(index, "discount", event.target.value)}
                          className="w-20 rounded border border-slate-300 px-2 py-1 text-sm disabled:bg-slate-50"
                        />
                      </TD>
                      <TD>
                        <input
                          value={line.amount}
                          disabled={!canCorrect}
                          aria-label={`Montant ligne ${index + 1}`}
                          onChange={(event) => updateLine(index, "amount", event.target.value)}
                          className="w-24 rounded border border-slate-300 px-2 py-1 text-sm disabled:bg-slate-50"
                        />
                      </TD>
                    </TR>
                  ))}
                </tbody>
              </Table>
            </div>
          </div>

          <div className="mt-5 flex flex-wrap justify-end gap-2">
            <Button variant="secondary" onClick={handleSave} disabled={!canCorrect} loading={actions.correct.busy}>
              Enregistrer les corrections
            </Button>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="Décision comptable"
          subtitle={invoice.rejection_reason ? `Motif du rejet : ${invoice.rejection_reason}` : undefined}
        />
        <CardBody>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="success"
              onClick={() => actions.validate.run(invoice.id)}
              disabled={!canCorrect}
              loading={actions.validate.busy}
            >
              Valider la facture
            </Button>
            <Button variant="danger" onClick={() => setShowReject(true)} disabled={!canCorrect}>
              Rejeter la facture
            </Button>
            {canCreateBill && (
              <Button onClick={() => actions.createVendorBill.run(invoice.id)} loading={actions.createVendorBill.busy}>
                Créer la Vendor Bill Odoo
              </Button>
            )}
          </div>
        </CardBody>
      </Card>

      <Modal
        open={showReject}
        title="Rejeter la facture"
        onClose={() => setShowReject(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowReject(false)}>Annuler</Button>
            <Button
              variant="danger"
              disabled={!reason.trim()}
              loading={actions.reject.busy}
              onClick={async () => {
                const result = await actions.reject.run(invoice.id, reason.trim());
                if (result) setShowReject(false);
              }}
            >
              Confirmer le rejet
            </Button>
          </>
        }
      >
        <Textarea
          label="Motif obligatoire"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="Ex. : montant HT différent du bon de commande."
          rows={3}
        />
      </Modal>
    </div>
  );
}
