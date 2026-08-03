"""Application FastAPI SmartInvoice.

Point d'entrée : ``uvicorn app.main:app``. Les exceptions métier définies
dans ``app.core.exceptions`` sont traduites ici en réponses HTTP.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    anomalies,
    auth,
    catalog,
    config,
    invoices,
    metrics,
    odoo,
    tasks,
    users,
)
from app.core.config import get_settings
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    InvalidDocumentError,
    NotFoundError,
    OdooError,
    PermissionDeniedError,
    RateLimitExceededError,
    UserAlreadyExistsError,
)


def create_app() -> FastAPI:
    """Fabrique l'application FastAPI (tests inclus)."""
    app = FastAPI(
        title="SmartInvoice API",
        description="OCR & rapprochement automatique des factures fournisseurs.",
        version="0.4.0",
    )

    settings = get_settings()
    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(users.router, prefix="/api/users", tags=["users"])
    app.include_router(invoices.router, prefix="/api/invoices", tags=["invoices"])
    app.include_router(anomalies.router, prefix="/api/anomalies", tags=["anomalies"])
    app.include_router(odoo.router, prefix="/api/odoo/sync", tags=["odoo-sync"])
    app.include_router(config.router, prefix="/api/config", tags=["config"])
    app.include_router(
        catalog.suppliers_router, prefix="/api/suppliers", tags=["suppliers"]
    )
    app.include_router(
        catalog.purchase_orders_router,
        prefix="/api/purchase-orders",
        tags=["purchase-orders"],
    )
    app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
    app.include_router(metrics.router, prefix="", tags=["monitoring"])

    @app.exception_handler(AuthenticationError)
    async def _handle_authentication(
        _request: Request, exc: AuthenticationError
    ) -> JSONResponse:
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    @app.exception_handler(PermissionDeniedError)
    async def _handle_permission(
        _request: Request, exc: PermissionDeniedError
    ) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.exception_handler(RateLimitExceededError)
    async def _handle_rate_limit(
        _request: Request, exc: RateLimitExceededError
    ) -> JSONResponse:
        return JSONResponse(status_code=429, content={"detail": str(exc)})

    @app.exception_handler(NotFoundError)
    async def _handle_not_found(
        _request: Request, exc: NotFoundError
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(UserAlreadyExistsError)
    async def _handle_conflict(
        _request: Request, exc: UserAlreadyExistsError
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def _handle_conflict_generic(
        _request: Request, exc: ConflictError
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(InvalidDocumentError)
    async def _handle_invalid_document(
        _request: Request, exc: InvalidDocumentError
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(OdooError)
    async def _handle_odoo_error(
        _request: Request, exc: OdooError
    ) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    return app


app = create_app()
