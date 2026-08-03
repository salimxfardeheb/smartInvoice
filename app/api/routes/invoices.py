"""Endpoints « documents » : dépôt, historique, consultation et statuts.

L'upload manuel (multipart/form-data) accepte les formats PDF, JPG, JPEG et
PNG, valide le format et la lisibilité du document, puis stocke le fichier et
crée la facture liée au fournisseur fourni.
"""

from __future__ import annotations

import time
from datetime import date, datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile

from app.api.deps import (
    get_anomaly_repository,
    get_audit_log_repository,
    get_confirmation_service,
    get_invoice_service,
    get_matching_service,
    get_ocr_engine_dep,
    get_storage,
    get_task_manager,
    get_validation_service,
    require_permissions,
)
from app.core.exceptions import (
    ConflictError,
    DocumentNotFoundError,
    InvalidStatusTransitionError,
    NotFoundError,
    SmartInvoiceError,
)
from app.core.permissions import Permission
from app.core.metrics import get_metrics
from app.models.enums import AuditAction, InvoiceStatus, TaskKind
from app.models.user import User
from app.ocr.base import OcrEngine
from app.repositories import AnomalyRepository, AuditLogRepository, InvoiceRepository
from app.schemas.invoice import (
    BatchDepositResponse,
    BatchDepositResult,
    InvoiceListResponse,
    InvoiceRead,
    InvoiceStatusUpdate,
)
from app.schemas.matching import MatchingAnomalyRead, MatchingLineRead, MatchingRead
from app.schemas.task import TaskRead, task_read
from app.schemas.anomaly import AnomalyRead
from app.schemas.summary import DashboardSummary, PendingAnomaly
from app.schemas.validation import (
    AuditLogListResponse,
    AuditLogRead,
    InvoiceConfirm,
    InvoiceCorrection,
    InvoiceReject,
)
from app.services.confirmation_service import BuyerConfirmationService
from app.services.invoice_service import InvoiceService
from app.services.matching_service import MatchingService
from app.services.ocr_service import OcrService
from app.services.task_manager import TaskManager
from app.services.validation_service import ValidationService
from app.storage.base import Storage

router = APIRouter()

InvoiceServiceDep = Annotated[InvoiceService, Depends(get_invoice_service)]
TaskManagerDep = Annotated[TaskManager, Depends(get_task_manager)]
StorageDep = Annotated[Storage, Depends(get_storage)]
EngineDep = Annotated[OcrEngine, Depends(get_ocr_engine_dep)]
MatchingServiceDep = Annotated[MatchingService, Depends(get_matching_service)]
ValidationServiceDep = Annotated[ValidationService, Depends(get_validation_service)]
ConfirmationServiceDep = Annotated[
    BuyerConfirmationService, Depends(get_confirmation_service)
]
AuditLogRepoDep = Annotated[AuditLogRepository, Depends(get_audit_log_repository)]
AnomalyRepoDep = Annotated[AnomalyRepository, Depends(get_anomaly_repository)]
InvoiceReadPerm = Annotated[
    object, Depends(require_permissions(Permission.INVOICE_READ))
]
InvoiceDepositPerm = Annotated[
    object, Depends(require_permissions(Permission.INVOICE_DEPOSIT))
]
InvoiceValidatePerm = Annotated[
    object, Depends(require_permissions(Permission.INVOICE_VALIDATE))
]
InvoiceConfirmPerm = Annotated[
    object, Depends(require_permissions(Permission.INVOICE_CONFIRM))
]


def _filename_header(filename: str) -> str:
    """En-tête Content-Disposition sûr (ASCII fallback + encodage RFC 5987)."""
    ascii_name = filename.encode("ascii", errors="replace").decode()
    encoded = quote(filename)
    if encoded == ascii_name:
        return f'attachment; filename="{ascii_name}"'
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


@router.post(
    "",
    response_model=InvoiceRead,
    status_code=201,
    summary="Déposer une facture (upload manuel)",
)
def deposit_invoice(
    file: Annotated[UploadFile, File(description="Document : PDF, JPG, JPEG, PNG")],
    invoice_number: Annotated[str, Form(description="Numéro de la facture")],
    supplier_id: Annotated[int, Form(description="Identifiant du fournisseur")],
    issue_date: Annotated[
        date | None, Form(description="Date d'émission (AAAA-MM-JJ)")
    ] = None,
    service: InvoiceServiceDep = None,
    _: InvoiceDepositPerm = None,
) -> object:
    """Dépose une facture : validation du document, stockage et création."""
    return service.deposit(
        filename=file.filename or "document",
        content=file.file.read(),
        invoice_number=invoice_number,
        supplier_id=supplier_id,
        issue_date=issue_date,
    )


@router.post(
    "/batch",
    response_model=BatchDepositResponse,
    status_code=201,
    summary="Déposer plusieurs factures d'un coup (traitement par lot)",
)
def deposit_batch(
    files: Annotated[list[UploadFile], File(description="Documents à déposer")],
    invoice_numbers: Annotated[list[str], Form(description="Numéros (un par fichier)")],
    supplier_ids: Annotated[list[int], Form(description="Fournisseurs (un par fichier)")],
    service: InvoiceServiceDep = None,
    _: InvoiceDepositPerm = None,
) -> BatchDepositResponse:
    """Dépose un lot de factures (un fichier = une facture).

    ``invoice_numbers`` et ``supplier_ids`` doivent avoir la même longueur que
    ``files`` (le fichier *i* est déposé avec le numéro *i* et le fournisseur
    *i*). Chaque fichier est traité indépendamment : un échec (doublon,
    document illisible, fournisseur inconnu) ne bloque pas les autres.
    """
    if len(files) != len(invoice_numbers) or len(files) != len(supplier_ids):
        raise InvalidStatusTransitionError(
            "files, invoice_numbers et supplier_ids doivent avoir la même longueur."
        )

    results: list[BatchDepositResult] = []
    for index, file in enumerate(files):
        try:
            invoice = service.deposit(
                filename=file.filename or f"document-{index + 1}",
                content=file.file.read(),
                invoice_number=invoice_numbers[index],
                supplier_id=supplier_ids[index],
            )
            results.append(BatchDepositResult(filename=file.filename or "", invoice=invoice))
        except SmartInvoiceError as exc:
            results.append(
                BatchDepositResult(filename=file.filename or "", error=str(exc))
            )
    return BatchDepositResponse(items=results, total=len(results))


@router.get(
    "",
    response_model=InvoiceListResponse,
    summary="Historique des factures (tri et filtres)",
)
def list_invoices(
    status: InvoiceStatus | None = Query(default=None, description="Filtrer par statut"),
    supplier_id: int | None = Query(default=None, description="Filtrer par fournisseur"),
    issue_date_from: date | None = Query(default=None, description="Émise à partir de"),
    issue_date_to: date | None = Query(default=None, description="Émise jusqu'à"),
    created_from: datetime | None = Query(default=None, description="Déposée à partir de"),
    created_to: datetime | None = Query(default=None, description="Déposée jusqu'à"),
    sort: str = Query(default="created_at_desc", description="Mode de tri"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: InvoiceServiceDep = None,
    _: InvoiceReadPerm = None,
) -> InvoiceListResponse:
    """Liste paginée des factures, avec filtres combinables et tri."""
    items, total = service.list_invoices(
        status=status,
        supplier_id=supplier_id,
        issue_date_from=issue_date_from,
        issue_date_to=issue_date_to,
        created_from=created_from,
        created_to=created_to,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return InvoiceListResponse(items=items, total=total)


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="Synthèse du tableau de bord (comptes par statut, anomalies)",
)
def invoice_summary(
    service: InvoiceServiceDep = None,
    anomalies: AnomalyRepoDep = None,
    _: InvoiceReadPerm = None,
) -> DashboardSummary:
    """Retourne le nombre de factures par statut et les anomalies non résolues.

    Utilisé par le tableau de bord : comptage par statut via la pagination et
    liste des anomalies en attente (priorité aux plus anciennes).
    """
    by_status = {
        status.value: service.list_invoices(status=status, limit=1)[1]
        for status in InvoiceStatus
    }
    pending = [
        PendingAnomaly(
            id=anomaly.id,
            invoice_id=anomaly.invoice_id,
            invoice_number=anomaly.invoice.invoice_number,
            supplier_name=anomaly.invoice.supplier.name,
            category=anomaly.category,
            severity=anomaly.severity,
            message=anomaly.message,
            expected_value=anomaly.expected_value,
            actual_value=anomaly.actual_value,
            created_at=anomaly.created_at,
        )
        for anomaly in anomalies.list_unresolved(limit=100)
    ]
    return DashboardSummary(by_status=by_status, pending_anomalies=pending)


@router.get(
    "/{invoice_id}",
    response_model=InvoiceRead,
    summary="Consulter une facture (métadonnées)",
)
def get_invoice(
    invoice_id: int,
    service: InvoiceServiceDep = None,
    _: InvoiceReadPerm = None,
) -> object:
    """Retourne les métadonnées d'une facture."""
    return service.get_invoice(invoice_id)


@router.get(
    "/{invoice_id}/file",
    summary="Télécharger le fichier source d'une facture",
)
def get_invoice_file(
    invoice_id: int,
    service: InvoiceServiceDep = None,
    _: InvoiceReadPerm = None,
) -> Response:
    """Retourne le fichier original déposé (PDF ou image)."""
    invoice = service.get_invoice(invoice_id)
    content = service.get_source_file(invoice)
    if invoice.content_type is None:
        raise DocumentNotFoundError("Le type du fichier source est inconnu.")
    return Response(
        content=content,
        media_type=invoice.content_type,
        headers={
            "Content-Disposition": _filename_header(
                invoice.original_filename or f"facture-{invoice.id}"
            )
        },
    )


@router.post(
    "/{invoice_id}/process",
    response_model=TaskRead,
    status_code=202,
    summary="Lancer l'analyse OCR d'une facture (tâche asynchrone)",
)
def process_invoice(
    invoice_id: int,
    service: InvoiceServiceDep = None,
    manager: TaskManagerDep = None,
    engine: EngineDep = None,
    storage: StorageDep = None,
    _: InvoiceDepositPerm = None,
) -> TaskRead:
    """Planifie le pipeline OCR (chargement, reconnaissance, structuration).

    L'analyse est exécutée **en arrière-plan** : la requête retourne
    immédiatement un ``task_id`` (statut ``PENDING``/``RUNNING``) à interroger
    via ``GET /api/tasks/{task_id}``. La facture doit être « Déposée » ou
    « Erreur système » ; si elle est déjà « En cours d'analyse » (traitement
    concurrent), une réponse 409 est retournée.
    """
    invoice = service.get_invoice(invoice_id)
    if invoice.status is InvoiceStatus.ANALYZING:
        raise ConflictError(
            "Une analyse OCR est déjà en cours pour cette facture."
        )

    def run(task_manager: TaskManager) -> dict:
        timer = time.monotonic()
        with task_manager.session_factory() as session:
            worker_invoice = InvoiceRepository(session).get(invoice_id)
            ocr = OcrService(session, storage, engine=engine)
            updated = ocr.process(worker_invoice)
            session.commit()
        get_metrics().record(
            "ocr_pipeline_seconds",
            time.monotonic() - timer,
            success=updated.status is not InvoiceStatus.SYSTEM_ERROR,
        )
        return {
            "invoice_id": updated.id,
            "status": updated.status.value,
            "ocr_confidence_score": updated.ocr_confidence_score,
            "error_message": updated.error_message,
        }

    task_id = manager.submit(kind=TaskKind.OCR, invoice_id=invoice_id, run=run)
    task = manager.get_task(task_id)
    return task_read(task)


@router.post(
    "/{invoice_id}/match",
    response_model=MatchingRead,
    summary="Rapprocher une facture à son bon de commande (matching)",
)
def match_invoice(
    invoice_id: int,
    service: InvoiceServiceDep = None,
    matching: MatchingServiceDep = None,
    _: InvoiceReadPerm = None,
) -> MatchingRead:
    """Exécute le rapprochement facture ↔ bon de commande (phase 6).

    Compare le fournisseur, rapproche les lignes (produit, quantité, prix),
    compare les montants et la TVA, puis calcule et persiste le score de
    matching global sur la facture. Les anomalies détectées sont enregistrées
    par catégorie (montant, TVA, quantité, produit absent, doublon...).
    """
    invoice = service.get_invoice(invoice_id)
    timer = time.monotonic()
    result = matching.match(invoice)
    get_metrics().record(
        "matching_pipeline_seconds",
        time.monotonic() - timer,
        success=result.score is not None,
    )

    extracted = (invoice.extracted_data or {}).get("general") or {}
    reference = (
        extracted.get("purchase_order_reference")
        if isinstance(extracted, dict)
        else None
    )
    return MatchingRead(
        invoice_id=result.invoice_id,
        purchase_order_reference=reference,
        supplier_match=result.supplier_match,
        duplicate_found=result.duplicate_found,
        score=result.score,
        lines=[
            MatchingLineRead(
                line_number=line.invoice_line.line_number,
                description=line.invoice_line.description,
                product_ref=line.invoice_line.product_ref,
                quantity=line.invoice_line.quantity,
                unit_price=line.invoice_line.unit_price,
                purchase_order_line_odoo_id=line.invoice_line.purchase_order_line_odoo_id,
                quantity_matched=line.quantity_matched,
                unit_price_matched=line.unit_price_matched,
                quantity_delta=line.quantity_delta,
                unit_price_delta=line.unit_price_delta,
            )
            for line in result.line_matches
        ],
        anomalies=[
            MatchingAnomalyRead(
                category=anomaly.category,
                severity=anomaly.severity,
                message=anomaly.message,
                expected_value=anomaly.expected_value,
                actual_value=anomaly.actual_value,
            )
            for anomaly in result.anomalies
        ],
    )


@router.post(
    "/{invoice_id}/status",
    response_model=InvoiceRead,
    summary="Changer le statut d'une facture (transitions validées)",
)
def update_invoice_status(
    invoice_id: int,
    payload: InvoiceStatusUpdate,
    service: InvoiceServiceDep = None,
    _: InvoiceValidatePerm = None,
) -> object:
    """Applique une transition de statut si elle est valide (409 sinon)."""
    invoice = service.get_invoice(invoice_id)
    return service.transition_status(invoice, payload.status, reason=payload.reason)


@router.post(
    "/{invoice_id}/validate",
    response_model=InvoiceRead,
    summary="Valider une facture",
)
def validate_invoice(
    invoice_id: int,
    service: InvoiceServiceDep = None,
    validation: ValidationServiceDep = None,
    user: User = Depends(require_permissions(Permission.INVOICE_VALIDATE)),
) -> object:
    """Valide une facture « À vérifier » (action tracée dans le journal d'audit)."""
    invoice = service.get_invoice(invoice_id)
    return validation.validate(invoice, user)


@router.post(
    "/{invoice_id}/reject",
    response_model=InvoiceRead,
    summary="Rejeter une facture (motif obligatoire)",
)
def reject_invoice(
    invoice_id: int,
    payload: InvoiceReject,
    service: InvoiceServiceDep = None,
    validation: ValidationServiceDep = None,
    user: User = Depends(require_permissions(Permission.INVOICE_VALIDATE)),
) -> object:
    """Rejette une facture avec un motif obligatoire (tracé dans l'audit)."""
    invoice = service.get_invoice(invoice_id)
    return validation.reject(invoice, user, payload.reason)


@router.put(
    "/{invoice_id}/correct",
    response_model=InvoiceRead,
    summary="Corriger manuellement les données extraites d'une facture",
)
def correct_invoice(
    invoice_id: int,
    payload: InvoiceCorrection,
    service: InvoiceServiceDep = None,
    validation: ValidationServiceDep = None,
    user: User = Depends(require_permissions(Permission.INVOICE_CORRECT)),
) -> object:
    """Corrige les champs et/ou les lignes d'une facture « À vérifier »."""
    invoice = service.get_invoice(invoice_id)
    return validation.correct(invoice, user, payload)


@router.post(
    "/{invoice_id}/vendor-bill",
    response_model=InvoiceRead,
    summary="Créer la Vendor Bill Odoo (account.move) d'une facture validée",
)
def create_vendor_bill(
    invoice_id: int,
    service: InvoiceServiceDep = None,
    validation: ValidationServiceDep = None,
    user: User = Depends(require_permissions(Permission.INVOICE_VALIDATE)),
) -> object:
    """Génère l'``account.move`` Odoo et lie le ``move_id`` à la facture."""
    invoice = service.get_invoice(invoice_id)
    return validation.create_vendor_bill(invoice, user)


@router.get(
    "/{invoice_id}/audit-logs",
    response_model=AuditLogListResponse,
    summary="Journal d'audit d'une facture (paginé)",
)
def list_audit_logs(
    invoice_id: int,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: InvoiceServiceDep = None,
    audit_logs: AuditLogRepoDep = None,
    _: object = Depends(require_permissions(Permission.JOURNAL_READ)),
) -> AuditLogListResponse:
    """Retourne le journal d'audit d'une facture, paginé (plus récentes d'abord)."""
    service.get_invoice(invoice_id)  # 404 si la facture n'existe pas
    items = audit_logs.list_by_invoice_paginated(invoice_id, limit=limit, offset=offset)
    total = audit_logs.count_by_invoice(invoice_id)
    return AuditLogListResponse(items=[AuditLogRead.model_validate(log) for log in items], total=total)


@router.post(
    "/{invoice_id}/confirm",
    response_model=InvoiceRead,
    summary="Confirmer les quantités/produits d'une facture (acheteur)",
)
def confirm_invoice(
    invoice_id: int,
    payload: InvoiceConfirm,
    service: InvoiceServiceDep = None,
    confirmation: ConfirmationServiceDep = None,
    user: User = Depends(require_permissions(Permission.INVOICE_CONFIRM)),
) -> object:
    """L'acheteur confirme (et éventuellement corrige) les quantités/produits.

    Les valeurs fournies écrasent celles des lignes concernées et les
    anomalies confirmables (quantité, produit absent, prix) encore ouvertes
    sont marquées résolues. L'action est tracée dans le journal d'audit.
    """
    invoice = service.get_invoice(invoice_id)
    return confirmation.confirm(invoice, user, payload)


@router.post(
    "/{invoice_id}/retry",
    response_model=TaskRead,
    status_code=202,
    summary="Ré-analyser une facture en « Erreur système » (tâche asynchrone)",
)
def retry_invoice(
    invoice_id: int,
    service: InvoiceServiceDep = None,
    manager: TaskManagerDep = None,
    engine: EngineDep = None,
    storage: StorageDep = None,
    audit_logs: AuditLogRepoDep = None,
    user: User = Depends(require_permissions(Permission.INVOICE_DEPOSIT)),
) -> TaskRead:
    """Relance le pipeline OCR d'une facture « Erreur système ».

    Exige l'état « Erreur système » (409 sinon) et trace une entrée d'audit
    ``re_analyse`` précisant le contexte avant de planifier la ré-analyse.
    """
    invoice = service.get_invoice(invoice_id)
    if invoice.status is not InvoiceStatus.SYSTEM_ERROR:
        raise InvalidStatusTransitionError(
            "Seules les factures « Erreur système » peuvent être relancées "
            f"(état actuel : « {invoice.status.value} »)."
        )
    audit_logs.create(
        invoice_id=invoice.id,
        user_id=user.id,
        action=AuditAction.REPROCESSED,
        message="Ré-analyse demandée pour une facture en erreur système.",
        details={
            "previous_status": invoice.status.value,
            "previous_error": invoice.error_message,
        },
    )

    def run(task_manager: TaskManager) -> dict:
        timer = time.monotonic()
        with task_manager.session_factory() as session:
            worker_invoice = InvoiceRepository(session).get(invoice_id)
            ocr = OcrService(session, storage, engine=engine)
            updated = ocr.process(worker_invoice)
            session.commit()
        get_metrics().record(
            "ocr_pipeline_seconds",
            time.monotonic() - timer,
            success=updated.status is not InvoiceStatus.SYSTEM_ERROR,
        )
        return {
            "invoice_id": updated.id,
            "status": updated.status.value,
            "ocr_confidence_score": updated.ocr_confidence_score,
            "error_message": updated.error_message,
        }

    task_id = manager.submit(kind=TaskKind.OCR, invoice_id=invoice_id, run=run)
    return task_read(manager.get_task(task_id))


@router.post(
    "/{invoice_id}/anomalies/{anomaly_id}/resolve",
    response_model=AnomalyRead,
    summary="Résoudre une anomalie d'une facture",
)
def resolve_invoice_anomaly(
    invoice_id: int,
    anomaly_id: int,
    service: InvoiceServiceDep = None,
    anomalies: AnomalyRepoDep = None,
    _: InvoiceValidatePerm = None,
) -> AnomalyRead:
    """Marque comme résolue une anomalie appartenant à la facture donnée."""
    service.get_invoice(invoice_id)  # 404 si la facture n'existe pas
    anomaly = anomalies.get(anomaly_id)
    if anomaly is None or anomaly.invoice_id != invoice_id:
        raise NotFoundError("Anomalie introuvable pour cette facture.")
    return _anomaly_to_read(anomalies.resolve(anomaly))


def _anomaly_to_read(anomaly) -> AnomalyRead:
    """Schéma de sortie d'une anomalie (contexte facture/fournisseur)."""
    invoice = anomaly.invoice
    return AnomalyRead(
        id=anomaly.id,
        invoice_id=anomaly.invoice_id,
        invoice_number=invoice.invoice_number,
        supplier_name=invoice.supplier.name if invoice.supplier else None,
        category=anomaly.category,
        severity=anomaly.severity,
        message=anomaly.message,
        expected_value=anomaly.expected_value,
        actual_value=anomaly.actual_value,
        resolved=anomaly.resolved,
        resolved_at=anomaly.resolved_at,
        created_at=anomaly.created_at,
    )
