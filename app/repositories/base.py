"""Repository générique : opérations CRUD communes à tous les agrégats."""

from __future__ import annotations

from typing import Any, ClassVar, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """CRUD générique sur une entité SQLAlchemy.

    L'attribut de classe ``model`` doit être redéfini par chaque sous-classe.
    Toutes les méthodes travaillent sur la session fournie à la construction ;
    la validation (commit) reste à la charge de l'appelant afin de permettre
    des transactions unitaires.
    """

    model: ClassVar[type[ModelT]]

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, instance: ModelT) -> ModelT:
        """Enregistre une nouvelle entité dans la session.

        Un ``flush`` est déclenché afin que la clé primaire soit disponible
        immédiatement après l'appel ; la transaction reste ouverte jusqu'au
        ``commit`` (ou annulée par un ``rollback``) par l'appelant.
        """
        self.session.add(instance)
        self.session.flush()
        return instance

    def get(self, obj_id: int) -> ModelT | None:
        """Retourne l'entité par clé primaire, ou ``None``."""
        return self.session.get(self.model, obj_id)

    def list(self, *, limit: int = 100, offset: int = 0) -> list[ModelT]:
        """Retourne les entités paginées, triées par ``id``."""
        stmt = (
            select(self.model).order_by(self.model.id).limit(limit).offset(offset)
        )
        return list(self.session.scalars(stmt))

    def count(self) -> int:
        """Retourne le nombre total d'entités."""
        stmt = select(func.count(self.model.id))
        return int(self.session.scalar(stmt) or 0)

    def update(self, instance: ModelT, **fields: Any) -> ModelT:
        """Met à jour les attributs fournis sur l'entité en session."""
        for key, value in fields.items():
            setattr(instance, key, value)
        return instance

    def delete(self, instance: ModelT) -> None:
        """Marque l'entité pour suppression dans la session."""
        self.session.delete(instance)
