"""Statut d'un amendement : lecture métier, dérivée de la raison de refus.

Le statut ne remplace jamais `Reason` : il en est déduit (`status_of`), ou imposé par la
consolidation quand elle sait mieux (série identique, sous-amendement).

Les statuts des amendements non adoptés (`predicted_*`, `undetermined`, `ignored`) viennent du sort
de l'amendement (`Amendment.outcome`) : ils sont imposés par la consolidation, jamais déduits d'une
raison de refus.
"""

import enum
from typing import Any

from engine.domain.refusal import Reason


class Status(enum.StrEnum):
    """Statut d'un amendement."""

    APPLIED = "applied"
    IDENTICAL = "identical"
    SUB_AMENDMENT = "sub_amendment"
    NOT_PARSED = "not_parsed"
    PENDING = "pending"
    AMBIGUOUS = "ambiguous"
    PREDICTED_FALLEN = "predicted_fallen"  # non adopté : serait tombé
    PREDICTED_ALIVE = "predicted_alive"  # non adopté : aurait pu s'appliquer
    UNDETERMINED = "undetermined"  # non adopté : pas de prédiction possible
    IGNORED = "ignored"  # non voté (retiré, irrecevable…)


STATUS_OF_REASON: dict[Reason, Status] = {
    Reason.AMBIGUOUS: Status.AMBIGUOUS,
    Reason.QUOTE_MULTIPLE: Status.AMBIGUOUS,
    Reason.TARGET_NOT_FOUND: Status.PENDING,
    Reason.TARGET_GONE: Status.PENDING,
    Reason.QUOTE_MISSING: Status.PENDING,
    Reason.UNRESOLVED_ARTICLE: Status.PENDING,
    Reason.INCONSISTENT_BLOCK: Status.PENDING,
    Reason.CONFLICT: Status.PENDING,
    Reason.OUT_OF_SCOPE: Status.NOT_PARSED,
}


def status_of(reason: Reason | None, result: Any) -> Status:
    """Statut déduit : appliqué si un résultat et pas de refus, sinon selon la raison."""
    if reason is None:
        if result is None:
            raise ValueError("ni résultat ni raison de refus")
        return Status.APPLIED
    return STATUS_OF_REASON[reason]
