"""Paliers de tolérance : écarts simples entre une citation et le texte, du plus sûr au moins sûr.

Fonctions pures sur des `str`. Un palier ne choisit jamais entre deux candidats : `writing.locate`
n'en accepte un que s'il est le seul, et le note dans la trace.
"""

import enum
import re
from collections.abc import Iterable


class Tolerance(enum.StrEnum):
    """Palier utilisé pour retrouver une citation, noté dans la trace. Du plus sûr au moins sûr."""

    TYPOGRAPHY = "typographie"
    APPROXIMATE = "mots_approches"


def loosest(tolerances: Iterable[Tolerance | None]) -> Tolerance | None:
    """Le palier le moins sûr de la liste, None si aucune tolérance n'a servi."""
    used = [t for t in tolerances if t is not None]
    return max(used, key=list(Tolerance).index, default=None)


_DASHES = "–—‐‒−"
_QUOTES = {"“": '"', "”": '"', "„": '"'}
_SEPARATOR = "\x01"  # une espace, ou un trait d'union entre deux lettres : « au delà », « au-delà »


def fold(text: str) -> tuple[str, list[int]]:
    """Texte plié (écarts typographiques effacés) et, par caractère plié, son indice d'origine.

    Pliés : tirets longs, guillemets anglais (les apostrophes le sont déjà par `normalize`),
    espaces multiples, espace de groupement d'un nombre (« 4 000 » = « 4000 »), trait d'union
    entre deux lettres (= espace).
    La liste a un élément de plus que le texte plié : la fin du texte d'origine.
    """
    chars: list[str] = []
    origin: list[int] = []
    for i, char in enumerate(text):
        before, after = text[i - 1 : i], text[i + 1 : i + 2]
        char = _QUOTES.get(char, "-" if char in _DASHES else char)
        if char == " ":
            if re.fullmatch(r"\d", before) and re.match(r"\d{3}(?!\d)", text[i + 1 :]):
                continue  # groupement de milliers
            if chars and chars[-1] == _SEPARATOR:
                continue
            char = _SEPARATOR
        elif char == "-" and before.isalpha() and after.isalpha():
            if chars and chars[-1] == _SEPARATOR:
                continue
            char = _SEPARATOR
        chars.append(char)
        origin.append(i)
    return "".join(chars), [*origin, len(text)]


def _one_edit(a: str, b: str) -> bool:
    """Vrai si `a` et `b` diffèrent d'une édition : substitution, ajout, retrait ou échange."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    if len(a) == len(b):
        return a[i + 1 :] == b[i + 1 :] or (
            a[i] == b[i + 1 : i + 2] and a[i + 2 :] == b[i + 2 :] and a[i + 1 : i + 2] == b[i]
        )
    short, long = sorted((a, b), key=len)
    return short[i:] == long[i + 1 :]


def _typo(cited: str, found: str) -> bool:
    """Vrai si `found` est une coquille de `cited` : un mot long, sans chiffre, bords intacts.

    Les bords intacts écartent les pluriels, féminins et préfixes, qui sont d'autres mots.
    """
    return (
        min(len(cited), len(found)) >= 5
        and not any(c.isdigit() for c in cited + found)
        and cited[0] == found[0]
        and cited[-1] == found[-1]
        and _one_edit(cited, found)
    )


_WORD = re.compile(r"[\w'’-]+")
MIN_WORDS, MIN_CHARS = 2, 12


def approximate(text: str, line: str) -> list[tuple[int, int]]:
    """Plages de `line` qui sont la citation `text` à une coquille près.

    Citation d'au moins 2 mots et 12 caractères, qui commence et finit par un mot. Mêmes mots, mêmes
    séparateurs ; un seul mot diffère et c'est une coquille (`_typo`).
    """
    cited = list(_WORD.finditer(text))
    if (
        len(cited) < MIN_WORDS
        or len(text) < MIN_CHARS
        or cited[0].start() != 0
        or cited[-1].end() != len(text)
    ):
        return []
    separators = [text[a.end() : b.start()] for a, b in zip(cited, cited[1:], strict=False)]
    words = list(_WORD.finditer(line))
    found = []
    for k in range(len(words) - len(cited) + 1):
        window = words[k : k + len(cited)]
        if [
            line[a.end() : b.start()] for a, b in zip(window, window[1:], strict=False)
        ] != separators:
            continue
        pairs = [(c.group(), w.group()) for c, w in zip(cited, window, strict=True)]
        differing = [(c, w) for c, w in pairs if c != w]
        if len(differing) == 1 and _typo(*differing[0]):
            found.append((window[0].start(), window[-1].end()))
    return found
