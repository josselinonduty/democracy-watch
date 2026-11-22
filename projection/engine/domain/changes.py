"""Mots ajoutés et retirés entre deux versions : de quoi reconnaître un quasi-doublon.

Les identifiants de mots sont stables : un mot repris tel quel garde le sien, un mot écrit en reçoit
un nouveau. La différence se lit donc sur les identifiants, sans alignement de texte. Les blancs
sont écartés : « a  b » et « a b » ne diffèrent pas. Seuls les mots comptent, pas leur
emplacement : c'est la définition du quasi-doublon (mêmes mots ajoutés et retirés).
"""

from collections import Counter

from engine.domain.version import Version


def _words(version: Version) -> dict[str, str]:
    """Texte des mots non blancs de la version, par identifiant."""
    return {
        word.id: word.text
        for article in version.articles
        for paragraph in article.paragraphs
        for word in paragraph.words
        if not word.text.isspace()
    }


def word_changes(before: Version, after: Version) -> tuple[Counter[str], Counter[str]]:
    """Les mots retirés et les mots ajoutés par le passage de `before` à `after`, comptés."""
    old, new = _words(before), _words(after)
    removed = Counter(text for word_id, text in old.items() if word_id not in new)
    added = Counter(text for word_id, text in new.items() if word_id not in old)
    return removed, added
