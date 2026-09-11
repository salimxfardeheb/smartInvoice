"""Gestion des comptes utilisateurs SmartInvoice (CLI d'administration).

Permet de créer un compte et d'en réinitialiser le mot de passe sans passer
par l'API — utile pour amorcer le premier administrateur sur une base neuve,
ou dépanner un compte dont le mot de passe est perdu.

Usage :
    python scripts/manage_users.py create admin admin@exemple.fr \
        --role Administrateur --full-name "Salim Fardeheb"
    python scripts/manage_users.py password admin
    python scripts/manage_users.py list

Le mot de passe n'est jamais passé en argument (il serait visible dans la
liste des processus) : il est demandé de façon masquée, ou lu sur l'entrée
standard avec ``--password-stdin`` pour l'automatisation :

    echo 'motdepasse' | python scripts/manage_users.py password admin --password-stdin

Retourne le code 0 en cas de succès, 1 en cas d'erreur.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

# Raccourci : rend le projet importable quand le script est lancé directement
# (``python scripts/manage_users.py``) depuis n'importe quel répertoire.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.enums import UserRole  # noqa: E402
from app.models.user import User  # noqa: E402
from app.repositories.refresh_token_repository import (  # noqa: E402
    RefreshTokenRepository,
)
from app.repositories.user_repository import UserRepository  # noqa: E402
from app.schemas.user import UserCreate  # noqa: E402

# Longueurs imposées par ``UserCreate`` ; rappelées ici pour valider aussi la
# modification de mot de passe, qui ne passe pas par ce schéma.
_PASSWORD_MIN_LENGTH = 8
_PASSWORD_MAX_LENGTH = 128


def _read_password(*, from_stdin: bool, confirm: bool) -> str:
    """Lit un mot de passe sans le faire apparaître dans la ligne de commande.

    Avec ``from_stdin``, la première ligne de l'entrée standard est utilisée
    telle quelle (automatisation). Sinon la saisie est masquée puis confirmée,
    afin qu'une faute de frappe ne produise pas un compte inaccessible.
    """
    if from_stdin:
        password = sys.stdin.readline().rstrip("\n")
        if not password:
            raise ValueError("Aucun mot de passe reçu sur l'entrée standard.")
        return password

    password = getpass.getpass("Mot de passe : ")
    if confirm and password != getpass.getpass("Confirmation : "):
        raise ValueError("Les deux saisies ne correspondent pas.")
    return password


def _check_password_length(password: str) -> None:
    """Vérifie la longueur du mot de passe (même règle que l'API)."""
    if not _PASSWORD_MIN_LENGTH <= len(password) <= _PASSWORD_MAX_LENGTH:
        raise ValueError(
            f"Le mot de passe doit compter entre {_PASSWORD_MIN_LENGTH} et "
            f"{_PASSWORD_MAX_LENGTH} caractères."
        )


def _warn_on_email_case_twin(users: UserRepository, email: str) -> None:
    """Signale un compte dont l'email ne diffère que par la casse.

    ``EmailStr`` n'abaisse que le domaine : ``Admin@exemple.fr`` et
    ``admin@exemple.fr`` sont deux valeurs distinctes pour la contrainte
    d'unicité, alors que les messageries les traitent comme une seule boîte.
    La création n'est pas bloquée (l'API l'autorise aussi), mais l'ambiguïté
    est signalée plutôt que silencieuse.
    """
    twin = next(
        (
            existing
            for existing in users.filter(limit=1000)
            if existing.email.lower() == email.lower()
        ),
        None,
    )
    if twin is not None:
        print(
            f"Attention : « {twin.username} » utilise déjà {twin.email}, "
            f"qui ne diffère que par la casse.",
            file=sys.stderr,
        )


def _find_user(users: UserRepository, identifier: str) -> User:
    """Retourne l'utilisateur désigné par son nom ou son email."""
    user = users.get_by_username(identifier) or users.get_by_email(identifier)
    if user is None:
        raise ValueError(f"Aucun utilisateur nommé « {identifier} ».")
    return user


def _create(args: argparse.Namespace) -> int:
    """Crée un compte utilisateur."""
    with SessionLocal() as session:
        users = UserRepository(session)
        # Unicité vérifiée avant la saisie : inutile de faire taper deux fois
        # un mot de passe pour un compte qui sera refusé. La contrainte de la
        # base reste l'autorité finale (voir le rattrapage d'``IntegrityError``
        # dans ``main`` : normalisation de l'email, créations concurrentes).
        if users.get_by_username(args.username) is not None:
            raise ValueError(f"Le nom « {args.username} » est déjà pris.")
        if users.get_by_email(args.email) is not None:
            raise ValueError(f"L'email « {args.email} » est déjà utilisé.")
        _warn_on_email_case_twin(users, args.email)

        password = _read_password(from_stdin=args.password_stdin, confirm=True)

        # Le schéma de l'API valide le format de l'email et les longueurs : on
        # le réutilise pour que la CLI n'accepte pas ce que l'API refuserait.
        payload = UserCreate(
            username=args.username,
            email=args.email,
            password=password,
            full_name=args.full_name,
            role=UserRole(args.role),
        )

        user = users.create(
            username=payload.username,
            email=payload.email,
            hashed_password=hash_password(payload.password),
            full_name=payload.full_name,
            role=payload.role,
            is_active=not args.inactive,
        )
        session.commit()
        print(
            f"Compte créé : id={user.id} « {user.username} » "
            f"({user.email}), rôle {user.role.value}, "
            f"{'actif' if user.is_active else 'inactif'}."
        )
    return 0


def _password(args: argparse.Namespace) -> int:
    """Remplace le mot de passe d'un compte et révoque ses sessions."""
    with SessionLocal() as session:
        users = UserRepository(session)
        user = _find_user(users, args.identifier)

        password = _read_password(from_stdin=args.password_stdin, confirm=True)
        _check_password_length(password)

        users.update(user, hashed_password=hash_password(password))
        # Même politique que ``AuthService.change_password`` : un mot de passe
        # changé invalide les sessions ouvertes, sinon un refresh token volé
        # resterait utilisable après la réinitialisation.
        revoked = RefreshTokenRepository(session).revoke_all_for_user(user.id)
        session.commit()
        print(
            f"Mot de passe mis à jour pour « {user.username} » "
            f"({revoked} session(s) révoquée(s))."
        )
    return 0


def _list(args: argparse.Namespace) -> int:
    """Affiche les comptes existants."""
    with SessionLocal() as session:
        users = UserRepository(session).filter(
            active=True if args.active_only else None, limit=args.limit
        )
        if not users:
            print("Aucun utilisateur.")
            return 0
        print(f"{'id':>4}  {'nom':<20} {'email':<32} {'rôle':<16} état")
        for user in users:
            state = "actif" if user.is_active else "inactif"
            print(
                f"{user.id:>4}  {user.username:<20} {user.email:<32} "
                f"{user.role.value:<16} {state}"
            )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gestion des comptes utilisateurs SmartInvoice.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="crée un compte utilisateur.")
    create.add_argument("username", help="nom de connexion (3 à 50 caractères).")
    create.add_argument("email", help="adresse email (unique).")
    create.add_argument(
        "--full-name", default=None, help="nom complet affiché (facultatif)."
    )
    create.add_argument(
        "--role",
        default=UserRole.ACCOUNTANT.value,
        choices=[role.value for role in UserRole],
        help="rôle métier du compte (défaut : %(default)s).",
    )
    create.add_argument(
        "--inactive",
        action="store_true",
        help="crée le compte désactivé (il ne pourra pas se connecter).",
    )
    create.set_defaults(func=_create)

    password = subparsers.add_parser(
        "password", help="remplace le mot de passe d'un compte."
    )
    password.add_argument("identifier", help="nom de connexion ou email du compte.")
    password.set_defaults(func=_password)

    for subparser in (create, password):
        subparser.add_argument(
            "--password-stdin",
            action="store_true",
            help="lit le mot de passe sur l'entrée standard au lieu de le demander.",
        )

    listing = subparsers.add_parser("list", help="liste les comptes existants.")
    listing.add_argument(
        "--active-only", action="store_true", help="n'affiche que les comptes actifs."
    )
    listing.add_argument(
        "--limit", type=int, default=100, help="nombre maximum de comptes affichés."
    )
    listing.set_defaults(func=_list)

    args = parser.parse_args(argv)

    try:
        return args.func(args)
    except ValidationError as exc:
        for error in exc.errors():
            field = ".".join(str(part) for part in error["loc"]) or "(racine)"
            print(f"{field} : {error['msg']}", file=sys.stderr)
        return 1
    except IntegrityError:
        # Contrainte d'unicité de la base : nom ou email déjà pris malgré la
        # pré-vérification (casse de l'email normalisée par ``EmailStr``, ou
        # création concurrente entre la lecture et l'insertion).
        print(
            "Un compte porte déjà ce nom ou cet email.",
            file=sys.stderr,
        )
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - erreur d'infrastructure
        print(f"Échec : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
