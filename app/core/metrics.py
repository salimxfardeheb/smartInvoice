"""Métriques de fonctionnement exposées sur ``GET /metrics``.

Mise en œuvre volontairement légère (compteurs + histogrammes simplifiés),
sans dépendance Prometheus client : le format texte est conforme au protocole
d'exposition Prometheus, ce qui suffit au scraping.

Les points mesurés :
- durée et statut des pipelines OCR et matching ;
- longueur de la file de tâches (par état) ;
- total des job en échec.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict


def _sanitize(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("_",) else "_" for c in name)


class Metrics:
    """Registre thread-safe de compteurs, jauges et histogrammes simplifiés."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # nom -> valeur (compteurs / jauges)
        self._values: dict[str, float] = defaultdict(float)
        # nom -> {label_json: count}
        self._counters: dict[str, dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        # nom -> {label_json: [total, count]}
        self._histograms: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: defaultdict(lambda: [0.0, 0.0])
        )

    def increment(self, name: str, labels: dict | None = None, delta: float = 1.0) -> None:
        with self._lock:
            if not labels:
                self._values[name] += delta
            else:
                key = self._label_key(labels)
                self._counters[name][key] += delta

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._values[name] = value

    def observe(self, name: str, seconds: float, labels: dict | None = None) -> None:
        with self._lock:
            key = self._label_key(labels or {})
            bucket = self._histograms[name][key]
            bucket[0] += seconds
            bucket[1] += 1.0

    def record(self, name: str, seconds: float, *, success: bool) -> None:
        """Equivalent de `observe` + counter de succès/échec sur une pipeline."""
        self.observe(name, seconds)
        self.increment(f"{_sanitize(name)}_total", delta=1.0)
        if not success:
            self.increment("jobs_failed_total", delta=1.0)

    @staticmethod
    def _label_key(labels: dict) -> str:
        return ",".join(f"{k}={v!r}" for k, v in sorted(labels.items()))

    # --- Export texte Prometheus ---------------------------------------------

    def render(self) -> str:
        lines: list[str] = []
        with self._lock:
            for name, value in sorted(self._values.items()):
                lines.append(f"# TYPE {name} gauge")
                lines.append(f"{name} {value:.0f}")
            for name, series in sorted(self._counters.items()):
                lines.append(f"# TYPE {name} counter")
                for key, value in sorted(series.items()):
                    label = f"{{{key}}}" if key else ""
                    lines.append(f"{name}{label} {value:.0f}")
            for name, series in sorted(self._histograms.items()):
                lines.append(f"# TYPE {name} histogram")
                for key, (total, count) in sorted(series.items()):
                    label = f"{{{key}}}" if key else ""
                    lines.append(f"{name}_sum{label} {total:.4f}")
                    lines.append(f"{name}_count{label} {count:.0f}")
        return "\n".join(lines) + "\n"


# Singleton d'application.
_metrics = Metrics()


def get_metrics() -> Metrics:
    """Retourne le registre de métriques partagé."""
    return _metrics