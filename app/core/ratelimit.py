"""Rate limiting (tentative de connexion / rafraîchissement).

Mise en œuvre en mémoire (fenêtre glissante simple, par clé) : suffisant pour
freiner le brute-force d'authentification sur une instance mono-process.
Une clé combine l'identifiant de l'utilisateur et l'adresse IP du client.
"""

from __future__ import annotations

import threading
import time


class SlidingWindowLimiter:
    """Limiteur en fenêtre glissante, thread-safe, sans dépendance externe."""

    def __init__(self, max_calls: int, window_seconds: int) -> None:
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._hits: dict[str, list[float]] = {}

    def allow(self, key: str) -> tuple[bool, int, float]:
        """Enregistre une tentative et répond (autorisé, restant, reset_seconds).

        ``restant`` = nombre de tentatives encore disponibles dans la fenêtre ;
        ``reset_seconds`` = temps (s) avant le début d'une nouvelle fenêtre.
        """
        now = time.monotonic()
        with self._lock:
            timestamps = self._hits.get(key, [])
            timestamps = [t for t in timestamps if now - t < self.window_seconds]
            if len(timestamps) >= self.max_calls:
                self._hits[key] = timestamps
                remaining = 0
                reset = self.window_seconds - (now - timestamps[0])
                return False, remaining, max(reset, 0.0)
            timestamps.append(now)
            self._hits[key] = timestamps
            return True, self.max_calls - len(timestamps), 0.0


# Limiteur partagé : limites paramétrées au premier usage (config).
_limiter: SlidingWindowLimiter | None = None
_limiter_lock = threading.Lock()


def get_limiter() -> SlidingWindowLimiter | None:
    """Retourne le limiteur partagé, ou ``None`` si désactivé.

    Les paramètres proviennent de la configuration ; le limiteur est
    (re)construit à chaque appel si les limites changent (rare).
    """
    global _limiter
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.rate_limit_enabled:
        return None
    with _limiter_lock:
        if (
            _limiter is None
            or _limiter.max_calls != settings.rate_limit_max
            or _limiter.window_seconds != settings.rate_limit_window_seconds
        ):
            _limiter = SlidingWindowLimiter(
                settings.rate_limit_max, settings.rate_limit_window_seconds
            )
        return _limiter