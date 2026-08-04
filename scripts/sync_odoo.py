"""Synchronisation périodique SmartInvoice → Odoo (CLI).

Point d'entrée d'une synchronisation programmée (cron / job scheduling) :
met à jour les référentiels Odoo dans le cache local. Pour l'instant seul le
synchroniseur de taux de change est branché (voir
:class:`app.services.odoo_service.OdooSyncService`).

Usage :
    python scripts/sync_odoo.py            # synchronise tout
    python scripts/sync_odoo.py --quiet    # sans sortie de détail

Retourne le code 0 en cas de succès, 1 en cas d'erreur (non bloquant pour le
planificateur si l'erreur est configurée comme non fatale).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Raccourci : rend le projet importable quand le script est lancé directement
# (``python scripts/sync_odoo.py``) depuis n'importe quel répertoire.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal  # noqa: E402
from app.services.odoo_service import OdooSyncService  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="n'affiche que le résumé (sans le détail des synchronisations).",
    )
    args = parser.parse_args(argv)

    try:
        with SessionLocal() as session:
            summary = OdooSyncService(session).sync_all()
            session.commit()
    except Exception as exc:  # pragma: no cover - erreur réelle non reproductible en test
        print(f"Échec de la synchronisation Odoo : {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"Synchronisation Odoo effectuée : {summary}")
    else:
        print(f"taux de change synchronisés : {summary['currency_rates']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
