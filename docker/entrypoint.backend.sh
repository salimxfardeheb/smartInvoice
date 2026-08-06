#!/usr/bin/env bash
#
# Point d'entrée de l'API : applique les migrations puis passe la main à la
# commande du conteneur (uvicorn par défaut).
#
# Les migrations sont jouées ici plutôt que dans un service à part car le
# schéma doit être à jour *avant* que la reprise au démarrage
# (app/services/startup_recovery.py) ne balaye les tâches orphelines.

set -euo pipefail

echo "[entrypoint] Application des migrations Alembic…"
alembic upgrade head
echo "[entrypoint] Schéma à jour."

exec "$@"
