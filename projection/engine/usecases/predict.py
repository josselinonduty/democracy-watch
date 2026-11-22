"""Prédiction du statut d'un amendement non adopté (étape 5 de la RFC).

Un amendement rejeté ou tombé ne modifie jamais le texte : on prédit seulement s'il serait tombé,
pour le comparer au sort réel. Il serait tombé si sa cible a disparu dans la version courante (un
amendement adopté avant lui l'a supprimée ou réécrite), ou si son effet, calculé sur le texte de
départ, entre en conflit avec celui d'un amendement adopté avant lui. Sans prédiction possible
(amendement non compris, cible introuvable ou ambiguë), le statut est `undetermined` : jamais de
devinette.

Fonction pure, comme `replay` : l'appelant fournit la version courante et les amendements adoptés
qui précèdent.
"""

from collections.abc import Sequence

from engine.domain.effect import Effect
from engine.domain.refusal import Reason, Refusal
from engine.domain.status import Status
from engine.domain.version import Version
from engine.usecases.compare import Relation, compare
from engine.usecases.draft import Draft
from engine.usecases.replay import replay


def predict(
    item: Draft,
    current: Version,
    reference: Version,
    before: Sequence[tuple[Draft, Effect]],
) -> Status:
    """Statut prédit de `item`, non adopté.

    `current` : la version courante au moment où il aurait été voté ; `reference` : la version
    d'origine ; `before` : les amendements adoptés qui le précèdent, avec leur effet seul sur
    `reference`.
    """
    try:
        _, effect = replay(reference, reference, item)
    except Refusal:
        return Status.UNDETERMINED
    try:
        replay(current, reference, item)
    except Refusal as refusal:
        gone = refusal.reason is Reason.TARGET_GONE
        return Status.PREDICTED_FALLEN if gone else Status.UNDETERMINED
    for adopted, adopted_effect in before:
        if not effect.interferes(adopted_effect):
            continue  # des effets disjoints commutent : pas de conflit possible
        try:
            if compare(item, adopted, reference, reference) is Relation.CONFLICT:
                return Status.PREDICTED_FALLEN
        except Refusal:
            return Status.UNDETERMINED
    return Status.PREDICTED_ALIVE
