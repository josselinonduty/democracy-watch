"""Entrées du moteur : texte de base et amendement, dans les termes du moteur.

La source de données (Tricoteuses…) construit ces types ; le moteur ne connaît aucun de ses champs.
"""

import dataclasses
import enum

from engine.domain.refusal import Reason, Refusal


@dataclasses.dataclass(frozen=True)
class Article:
    """Un article : ses alinéas, dans l'ordre (le numéro d'alinéa est la position, jamais stocké).

    `unchanged` : mention seule « (Non modifié) » sans texte connu ; `from_range` : issu d'une plage
    « Articles 2 à 4 », dont les lignes sont partagées. Dans ces deux cas le texte est inconnu.
    """

    number: str  # « PREMIER », « 5 BIS »
    lines: tuple[str, ...]
    unchanged: bool = False
    from_range: bool = False


@dataclasses.dataclass(frozen=True)
class Text:
    """Le texte de base d'une étape : ses articles, dans l'ordre."""

    uid: str
    articles: tuple[Article, ...]

    def find(self, number: str) -> Article:
        """L'unique article `number` dont le texte est connu ; sinon `Refusal`."""
        found = [article for article in self.articles if article.number == number]
        if len(found) != 1:
            raise Refusal(Reason.UNRESOLVED_ARTICLE, f"{len(found)} article(s) « {number} »")
        if found[0].unchanged or found[0].from_range:
            raise Refusal(
                Reason.UNRESOLVED_ARTICLE, "texte de l'article inconnu (inchangé ou plage)"
            )
        return found[0]


class Outcome(enum.StrEnum):
    """Sort réel d'un amendement, indépendant de la source."""

    ADOPTED = "adopted"
    REJECTED = "rejected"
    FALLEN = "fallen"
    NOT_VOTED = "not_voted"  # retiré, non soutenu, irrecevable, pas encore discuté


@dataclasses.dataclass(frozen=True)
class Amendment:
    """Un amendement. Le champ `alinea` de la source n'est qu'un indice : il n'est pas repris.

    `target_label` : article visé tel qu'écrit (« ART. 2 », « APRÈS ART. 3 »). `body_html` : le
    dispositif, un `<p>` par alinéa. `parent_id` : amendement modifié, pour un sous-amendement.
    `twin_group` : série d'amendements identiques votés ensemble.
    `decided_at` : date de la décision (ISO, UTC), None si inconnue. `outcome` : sort réel, None si
    inconnu (l'amendement est alors traité comme adopté : l'appelant a déjà filtré).
    """

    number: str  # « CE11 », « 3 (Rect) » : pour l'affichage
    target_label: str | None
    body_html: str
    id: str = ""
    parent_id: str | None = None
    twin_group: str | None = None
    decided_at: str | None = None
    outcome: Outcome | None = None
