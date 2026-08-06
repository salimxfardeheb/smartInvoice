"""Application FastAPI SmartInvoice.

Point d'entrée : ``uvicorn app.main:app``. Les exceptions métier définies
dans ``app.core.exceptions`` sont traduites ici en réponses HTTP.

.. warning::
   L'API doit être lancée avec **un seul worker** (``uvicorn --workers 1``).
   Le limiteur de débit (``core/ratelimit``), la file de jobs OCR
   (``services/task_manager``) et le registre de métriques (``core/metrics``)
   sont des singletons **en mémoire du processus** : avec plusieurs workers, la
   limite anti-brute-force est multipliée par leur nombre et ``/metrics`` ne
   renvoie que les compteurs du worker interrogé. Monter en charge via
   ``TASK_QUEUE_WORKERS`` (threads), pas via le nombre de workers Uvicorn.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.routes import (
    anomalies,
    auth,
    catalog,
    config,
    health,
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
from app.core.logging_config import configure_logging


logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]


def _build_lifespan(session_factory: SessionFactory | None):
    """Construit le gestionnaire de cycle de vie de l'application.

    Au démarrage, neutralise les tâches laissées « en cours » par un arrêt du
    serveur (voir :mod:`app.services.startup_recovery`). Le rapport est exposé
    sur ``app.state.recovery_report`` à des fins de diagnostic.

    ``session_factory`` permet aux tests de viser leur propre moteur ; en
    production, ``SessionLocal`` est résolu paresseusement au démarrage.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        from app.services.startup_recovery import (
            RecoveryReport,
            recover_orphan_tasks,
        )

        factory = session_factory
        if factory is None:
            from app.db.session import SessionLocal

            factory = SessionLocal

        app.state.recovery_report = RecoveryReport()
        try:
            with factory() as session:
                report = recover_orphan_tasks(session)
                session.commit()
            app.state.recovery_report = report
            if not report.is_empty:
                logger.warning(
                    "Reprise au démarrage : %s tâche(s) interrompue(s) "
                    "neutralisée(s), %s facture(s) débloquée(s) en « Erreur "
                    "système ».",
                    report.tasks_failed,
                    report.invoices_recovered,
                )
        except Exception:  # noqa: BLE001 - le démarrage ne doit pas échouer ici
            # Base injoignable ou schéma absent : on démarre quand même, les
            # requêtes échoueront explicitement plutôt que de bloquer le
            # déploiement sur un incident transitoire.
            logger.exception(
                "Reprise au démarrage impossible : des tâches peuvent rester "
                "« en cours » et des factures bloquées en « En cours d'analyse »."
            )

        yield

    return lifespan


def create_app(*, session_factory: SessionFactory | None = None) -> FastAPI:
    """Fabrique l'application FastAPI (tests inclus).

    ``session_factory`` n'est utilisée que par la reprise au démarrage ; les
    requêtes HTTP passent, elles, par la dépendance ``get_db``.
    """
    configure_logging()

    app = FastAPI(
        title="SmartInvoice API",
        description="OCR & rapprochement automatique des factures fournisseurs.",
        version="0.4.0",
        lifespan=_build_lifespan(session_factory),
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
    app.include_router(health.router, prefix="", tags=["monitoring"])

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
