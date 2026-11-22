"""Comparaison de deux amendements sur une même version : doublon, commutation, conflit.

On compare des effets, jamais des rédactions. La commutation se vérifie en appliquant réellement
les deux ordres (`replay`), sans la déduire de l'absence de conflit. Un amendement qui ne
s'applique pas seul sur `version` n'a pas d'effet à comparer : son `Refusal` est relevé.
"""

import enum

from engine.domain.changes import word_changes
from engine.domain.refusal import Refusal
from engine.domain.version import Version
from engine.usecases.draft import Draft
from engine.usecases.replay import replay


class Relation(enum.StrEnum):
    """Lien entre deux amendements, du plus fort au plus faible."""

    DUPLICATE = "duplicate"  # même empreinte : le second n'est pas une nouvelle modification
    NEAR_DUPLICATE = "near_duplicate"  # mêmes mots ajoutés et retirés, texte différent
    INDEPENDENT = "independent"  # commutent et leurs effets sont disjoints
    COMMUTE = "commute"  # commutent malgré des effets qui se touchent
    CONFLICT = "conflict"  # l'ordre change le résultat, ou l'un des ordres est refusé


def _then(version: Version, reference: Version, first: Draft, second: Draft) -> Version | None:
    """La version après `first` puis `second` ; None si le second ne s'applique plus."""
    try:
        after_first, _ = replay(version, reference, first)
        return replay(after_first, reference, second)[0]
    except Refusal:
        return None


def commute(a: Draft, b: Draft, version: Version, reference: Version) -> bool:
    """Vrai si `a` puis `b` et `b` puis `a` réussissent et donnent la même empreinte."""
    ab = _then(version, reference, a, b)
    ba = _then(version, reference, b, a)
    return ab is not None and ba is not None and ab.fingerprint() == ba.fingerprint()


def compare(a: Draft, b: Draft, version: Version, reference: Version) -> Relation:
    """La relation entre `a` et `b` appliqués sur `version`.

    `Refusal` si l'un d'eux n'y passe pas seul.

    `reference` : la version d'origine, où sont lus les numéros d'alinéa. Un quasi-doublon est
    reconnu avant le conflit : mêmes mots ajoutés et retirés, où que ce soit.
    """
    alone_a, effect_a = replay(version, reference, a)
    alone_b, effect_b = replay(version, reference, b)
    if alone_a.fingerprint() == alone_b.fingerprint() != version.fingerprint():
        return Relation.DUPLICATE
    changes_a, changes_b = word_changes(version, alone_a), word_changes(version, alone_b)
    if changes_a == changes_b and any(changes_a):
        return Relation.NEAR_DUPLICATE
    if not commute(a, b, version, reference):
        return Relation.CONFLICT
    return Relation.COMMUTE if effect_a.interferes(effect_b) else Relation.INDEPENDENT
