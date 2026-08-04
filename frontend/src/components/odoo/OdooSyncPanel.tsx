"use client";

import { useState } from "react";

import { api } from "@/lib/api-client";
import { formatCurrency, formatDate } from "@/lib/format";
import type { PurchaseOrderSyncResult, SupplierSyncResult } from "@/types";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";

function syncErrorMessage(cause: unknown): string {
  return cause instanceof Error ? cause.message : "Synchronisation impossible.";
}

/** Panneau de synchronisation des fournisseurs et des bons de commande. */
export function OdooSyncPanel() {
  const [supplierName, setSupplierName] = useState("");
  const [supplierResult, setSupplierResult] = useState<SupplierSyncResult | null>(null);
  const [supplierBusy, setSupplierBusy] = useState(false);
  const [supplierError, setSupplierError] = useState<string | null>(null);

  const [poReference, setPoReference] = useState("");
  const [poResult, setPoResult] = useState<PurchaseOrderSyncResult | null>(null);
  const [poBusy, setPoBusy] = useState(false);
  const [poError, setPoError] = useState<string | null>(null);

  async function handleSupplierSync(event: React.FormEvent) {
    event.preventDefault();
    if (!supplierName.trim() || supplierBusy) return;
    setSupplierBusy(true);
    setSupplierError(null);
    setSupplierResult(null);
    try {
      setSupplierResult(await api.syncSuppliers(supplierName.trim()));
    } catch (cause) {
      setSupplierError(syncErrorMessage(cause));
    } finally {
      setSupplierBusy(false);
    }
  }

  async function handlePurchaseOrderSync(event: React.FormEvent) {
    event.preventDefault();
    if (!poReference.trim() || poBusy) return;
    setPoBusy(true);
    setPoError(null);
    setPoResult(null);
    try {
      setPoResult(await api.syncPurchaseOrders(poReference.trim()));
    } catch (cause) {
      setPoError(syncErrorMessage(cause));
    } finally {
      setPoBusy(false);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader title="Synchroniser un fournisseur" subtitle="Depuis Odoo" />
        <CardBody className="space-y-4">
          {supplierError && (
            <Alert tone="danger" title="Échec de la synchronisation">
              {supplierError}
            </Alert>
          )}
          {supplierResult?.supplier && (
            <Alert tone="success" title="Fournisseur synchronisé">
              <p className="font-medium">{supplierResult.supplier.name}</p>
              <p className="text-xs">
                {supplierResult.supplier.vat ?? "N° TVA : —"}
                {supplierResult.supplier.email ? ` · ${supplierResult.supplier.email}` : ""}
              </p>
            </Alert>
          )}
          <form onSubmit={handleSupplierSync} className="space-y-3">
            <Input
              label="Nom du fournisseur"
              value={supplierName}
              onChange={(event) => setSupplierName(event.target.value)}
              placeholder="ex. ACME SAS"
              required
            />
            <div className="flex justify-end">
              <Button type="submit" loading={supplierBusy} disabled={!supplierName.trim()}>
                Synchroniser
              </Button>
            </div>
          </form>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Synchroniser un bon de commande" subtitle="Depuis Odoo" />
        <CardBody className="space-y-4">
          {poError && (
            <Alert tone="danger">{poError}</Alert>
          )}
          {poResult && (
            <Alert tone="success" title="Bon de commande synchronisé">
              <p className="text-xs">
                <b>{poResult.purchase_order.reference}</b>
                {poResult.purchase_order.supplier ? ` · ${poResult.purchase_order.supplier.name}` : ""}
                {" · "}
                {poResult.purchase_order.state ?? "état inconnu"}
                {poResult.purchase_order.total_amount != null
                  ? ` · ${formatCurrency(poResult.purchase_order.total_amount)}`
                  : ""}
                {poResult.purchase_order.date_order
                  ? ` · ${formatDate(poResult.purchase_order.date_order)}`
                  : ""}
              </p>
            </Alert>
          )}
          <form onSubmit={handlePurchaseOrderSync} className="space-y-3">
            <Input
              label="Référence du bon de commande (BC)"
              value={poReference}
              onChange={(event) => setPoReference(event.target.value)}
              placeholder="Ex. BC-2026-010"
              required
            />
            <div className="flex justify-end">
              <Button type="submit" loading={poBusy} disabled={!poReference.trim()}>
                Synchroniser
              </Button>
            </div>
          </form>
        </CardBody>
      </Card>
    </div>
  );
}