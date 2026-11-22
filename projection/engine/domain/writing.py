"""Règles d'écriture sur une ligne : repérage d'une ancre, insertion, recollement.

Fonctions pures sur des `str`. Les positions sont des indices de caractères du texte d'entrée.
"""

import dataclasses
import re
from typing import NamedTuple

from engine.domain import tolerance
from engine.domain.refusal import Reason, Refusal


@dataclasses.dataclass(frozen=True)
class Anchor:
    """Mots cités qui repèrent un point du texte.

    `occurrence` : rang explicite (1, 2… ; -1 = dernière) ; None = l'ancre doit être unique.
    """

    text: str
    occurrence: int | None = None


_ATTACHED = ",.);"  # ponctuation collée au mot qui précède
_OPENING = "'(«-"  # ponctuation à laquelle le mot suivant se colle


def _pattern(text: str) -> re.Pattern[str]:
    """Motif de `text` par mots entiers (voir `find_anchor`)."""
    first, last = text[0], text[-1]
    before = (r"(?<![\w-])" if re.match(r"\w", first) else "") + (
        r"(?<!\d[,.])" if first.isdigit() else ""
    )
    after = (r"(?![\w-])" if re.match(r"\w", last) else "") + (
        r"(?![,.]\d)" if last.isdigit() else ""
    )
    return re.compile(before + re.escape(text) + after)


def _select(found: list[tuple[int, int, int]], anchor: Anchor) -> tuple[int, int, int]:
    """L'occurrence voulue parmi les `found` ; refus si l'ancre est multiple ou absente."""
    rank = anchor.occurrence
    if rank is None and len(found) > 1:
        raise Refusal(Reason.QUOTE_MULTIPLE, f"« {anchor.text} » apparaît {len(found)} fois")
    if rank is None:
        rank = 1
    if rank == 0 or abs(rank) > len(found):
        raise Refusal(
            Reason.QUOTE_MISSING,
            f"« {anchor.text} » : occurrence {rank} absente ({len(found)} trouvée(s))",
        )
    return found[rank - 1 if rank > 0 else rank]


def _exact(texts: list[str], anchor: Anchor) -> list[tuple[int, int, int]]:
    pattern = _pattern(anchor.text)
    return [
        (index, match.start(), match.end())
        for index, text in enumerate(texts)
        for match in pattern.finditer(text)
    ]


def find_anchor(texts: list[str], anchor: Anchor) -> tuple[int, int, int]:
    """Repère l'ancre : (indice du texte, début, fin).

    Recherche par mots entiers et sensible à la casse : une frontière de mot n'est posée qu'aux
    bords de l'ancre qui sont des caractères de mot. Le trait d'union fait partie du mot
    (« porte » n'est pas dans « porte-parole ») ; l'apostrophe est une frontière. Un bord
    numérique ne coupe pas un nombre décimal (« 5 » n'est pas dans « 0,5 »). Les occurrences,
    non chevauchantes, sont comptées dans l'ordre sur l'ensemble des textes.
    """
    return _select(_exact(texts, anchor), anchor)


class Found(NamedTuple):
    """Ancre repérée : indice du texte, plage, et palier de tolérance (None : repérage exact)."""

    index: int
    start: int
    end: int
    tolerance: tolerance.Tolerance | None = None


def _folded(texts: list[str], anchor: Anchor) -> list[tuple[int, int, int]]:
    """Occurrences de l'ancre une fois les écarts typographiques effacés, en positions d'origine."""
    folded_anchor, _ = tolerance.fold(anchor.text)
    pattern = _pattern(folded_anchor)
    found = []
    for index, text in enumerate(texts):
        folded, origin = tolerance.fold(text)
        for match in pattern.finditer(folded):
            start, end = origin[match.start()], origin[match.end()]
            # Plier un trait d'union en espace ne doit pas couper un mot composé.
            if anchor.text[0].isalnum() and text[start - 1 : start] == "-" and start:
                continue
            if anchor.text[-1].isalnum() and text[end : end + 1] == "-":
                continue
            found.append((index, start, end))
    return found


def locate(texts: list[str], anchor: Anchor) -> Found:
    """Repère l'ancre : exactement, sinon par paliers de tolérance, du plus sûr au moins sûr.

    Un palier n'est tenté que si le précédent ne trouve rien, et ne vaut que s'il désigne un seul
    endroit : sinon refus `citation_absente`. L'ancre multiple (exacte) reste refusée telle quelle.
    """
    if found := _exact(texts, anchor):
        # Un rang explicite se compte sur toutes les variantes typographiques, pas sur les seules
        # occurrences exactes : sinon « la 1re » désignerait la 2e.
        if anchor.occurrence is not None and len(more := _folded(texts, anchor)) > len(found):
            return Found(*_select(more, anchor), tolerance.Tolerance.TYPOGRAPHY)
        return Found(*_select(found, anchor))
    if found := _folded(texts, anchor):
        return Found(*_select(found, anchor), tolerance.Tolerance.TYPOGRAPHY)
    if anchor.occurrence is None:
        close = [
            (index, start, end)
            for index, text in enumerate(texts)
            for start, end in tolerance.approximate(anchor.text, text)
        ]
        if len(close) == 1:
            return Found(*close[0], tolerance.Tolerance.APPROXIMATE)
        if close:
            raise Refusal(
                Reason.QUOTE_MISSING, f"« {anchor.text} » : {len(close)} candidats approchés"
            )
    return Found(*_select([], anchor))


def insert_at(text: str, point: int, new: str) -> str:
    """Insère `new` au point donné, avec les espaces nécessaires.

    `new` est collé à gauche s'il commence par `,` `.` `)` `;`, ou si le texte de gauche finit par
    `'` `(` `«` `-` ; à droite, aucune espace n'est ajoutée devant une telle ponctuation, une
    espace existante ou la fin du texte, ni si `new` finit par `'` `(` `«` `-`.
    """
    left, right = text[:point], text[point:]
    if left and not left.endswith(" ") and left[-1] not in _OPENING and new[0] not in _ATTACHED:
        left += " "
    if (
        right
        and not right.startswith(" ")
        and right[0] not in _ATTACHED
        and new[-1] not in _OPENING
    ):
        right = " " + right
    return left + new + right


def insert_edge(text: str, new: str, start: bool) -> str:
    """Insère `new` au début de l'alinéa, ou à sa fin avant la ponctuation finale.

    La ponctuation finale (`.` `;` `:`, avec l'espace qui la précède) est conservée telle quelle ;
    si `new` en porte déjà une alors que l'alinéa en a une, c'est un refus.
    """
    if start:
        return insert_at(text, 0, new)
    tail = re.search(r"\s*[.;:]\Z", text)
    if tail is None:
        return insert_at(text, len(text), new)
    if new[-1] in ".;:":
        raise Refusal(Reason.OUT_OF_SCOPE, "double ponctuation finale")
    return insert_at(text[: tail.start()], tail.start(), new) + tail.group()


def cut(text: str, start: int, end: int) -> str:
    """Retire `text[start:end]` et recolle localement.

    Deux espaces qui se touchent n'en font qu'une ; l'espace avant `,` ou `.` disparaît ;
    l'espace en bord de ligne, à l'endroit de la coupe, aussi.
    """
    left, right = text[:start], text[end:]
    if right[:1] in (",", "."):
        left = left.removesuffix(" ")
    elif left.endswith(" ") and right.startswith(" "):
        right = right[1:]
    if not left:
        right = right.lstrip(" ")
    if not right:
        left = left.rstrip(" ")
    return left + right


def cut_after(text: str, end: int) -> str:
    """Retire tout ce qui suit `end` (supprimer la fin)."""
    return text[:end].rstrip()


def rewrite_after(text: str, end: int, new: str) -> str:
    """Remplace tout ce qui suit `end` par `new` (réécrire la fin)."""
    return insert_at(text[:end], end, new)


def changed_span(old: str, new: str) -> tuple[int, int, str]:
    """Plus petite modification qui transforme `old` en `new` : (début, fin, remplacement).

    `old[début:fin]` est remplacé par `remplacement` ; on retire le préfixe et le suffixe communs.
    Les règles d'écriture ajustent les espaces autour d'une modification : elles sont donc
    comprises dans la plage, qui est celle de l'opération et d'elle seule.
    """
    limit = min(len(old), len(new))
    start = 0
    while start < limit and old[start] == new[start]:
        start += 1
    tail = 0
    while tail < limit - start and old[-1 - tail] == new[-1 - tail]:
        tail += 1
    return start, len(old) - tail, new[start : len(new) - tail]
