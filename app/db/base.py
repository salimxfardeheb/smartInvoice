"""Déclaration de base des modèles SQLAlchemy.

Toutes les tables partagent une convention de nommage des contraintes
(index, unicité, clés étrangères, checks, primaires) afin de disposer de
noms déterministes et stables entre les migrations et l'autogénération Alembic.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Classe de base déclarative de tous les modèles SmartInvoice."""

    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )
