"""Endpoints « documents » : dépôt, historique, consultation et statuts.

L'upload manuel (multipart/form-data) accepte les formats PDF, JPG, JPEG et
PNG, valide le format et la lisibilité du document, puis stocke le fichier et
crée la facture liée au fournisseur fourni.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile

from app.api.deps import get_invoice_service, require_permissions
from app.core.exceptions import DocumentNotFoundError
from app.core.permissions import Permission
from app.models.enums import InvoiceStatus
from app.schemas.invoice import InvoiceListResponse, InvoiceRead, InvoiceStatusUpdate
from app.services.invoice_service import InvoiceService

router = APIRouter()

InvoiceServiceDep = Annotated[InvoiceService, Depends(get_invoice_service)]
InvoiceReadPerm = Annotated[
    object, Depends(require_permissions(Permission.INVOICE_READ))
]
InvoiceDepositPerm = Annotated[
    object, Depends(require_permissions(Permission.INVOICE_DEPOSIT))
]
InvoiceValidatePerm = Annotated[
    object, Depends(require_permissions(Permission.INVOICE_VALIDATE))
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
