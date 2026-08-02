"""Application FastAPI SmartInvoice.

Point d'entrée : ``uvicorn app.main:app``. Les exceptions métier définies
dans ``app.core.exceptions`` sont traduites ici en réponses HTTP.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import auth, invoices, users
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    InvalidDocumentError,
    NotFoundError,
    PermissionDeniedError,
    UserAlreadyExistsError,
)


def create_app() -> FastAPI:
    """Fabrique l'application FastAPI (tests inclus)."""
    app = FastAPI(
        title="SmartInvoice API",
        description="OCR & rapprochement automatique des factures fournisseurs.",
        version="0.4.0",
    )

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(users.router, prefix="/api/users", tags=["users"])
    app.include_router(invoices.router, prefix="/api/invoices", tags=["invoices"])

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

    return app


app = create_app()
