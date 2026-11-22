"""Comparaison : empreinte de version, mots changés, commutation, doublon, conflit."""

import pytest

from engine.domain.changes import word_changes
from engine.domain.documents import Amendment, Article, Text
from engine.domain.effect import effect_of
from engine.domain.patch import conflicts
from engine.domain.refusal import Reason, Refusal
from engine.domain.version import Version
from engine.usecases.compare import Relation, commute, compare
from engine.usecases.draft import draft
from engine.usecases.replay import replay

LINES = (
    "I. – Le fait de vendre ce produit est puni d'une amende de 4 000 euros.",
    "II. – Le présent article entre en vigueur le 1er janvier 2027.",
)
TEXT = Text("T0", (Article("3", LINES),))
REF = Version.of(TEXT)


def amendment(number, *paragraphs):
    body = "".join(f"<p>{p}</p>" for p in paragraphs)
    return draft(TEXT, Amendment(number, "ART. 3", body, id=number))


def substitute(number, line, old, new):
    return amendment(
        number, f"À l'alinéa {line}, substituer au mot :", f"« {old} »", "le mot :", f"« {new} »."
    )


AMOUNT = substitute("A1", 1, "4 000", "10 000")
AMOUNT_AGAIN = substitute("A2", 1, "4 000", "10 000")
VERB = substitute("A3", 1, "vendre", "céder")
YEAR = substitute("A4", 2, "2027", "2028")
OTHER_AMOUNT = substitute("A5", 1, "4 000", "20 000")
REWRITE = amendment("A6", "Rédiger ainsi l'alinéa 1 :", "« Alinéa réécrit. »")
INSERT_1 = amendment("A7", "Après l'alinéa 1, insérer l'alinéa suivant :", "« Un. »")
INSERT_2 = amendment("A8", "Après l'alinéa 1, insérer l'alinéa suivant :", "« Deux. »")


def test_fingerprint_is_content_only():
    one, _ = replay(REF, REF, AMOUNT)
    two, _ = replay(REF, REF, AMOUNT_AGAIN)
    assert one.fingerprint() == two.fingerprint() != REF.fingerprint()
    assert one.word(next(w.id for w in one.find("3").paragraphs[0].words if w.text == "10"))


def test_fingerprint_does_not_confuse_paragraph_boundaries():
    def version(*lines):
        return Version.of(Text("T0", (Article("3", lines),)))

    assert version("a", "b").fingerprint() != version("a\x1fb").fingerprint()
    assert version("a", "b").fingerprint() != version("b", "a").fingerprint()


def test_word_changes_counts_added_and_removed_words_without_blanks():
    after, _ = replay(REF, REF, AMOUNT)
    removed, added = word_changes(REF, after)
    assert (removed, added) == ({"4": 1}, {"10": 1})  # « 000 » est repris tel quel
    assert word_changes(REF, REF) == ({}, {})


def test_deleted_article_removes_all_its_words():
    gone = Version.of(Text("T0", (Article("3", ()),)))
    removed, added = word_changes(REF, gone)
    assert not added and removed["Le"] == 2


def test_distinct_paragraphs_commute_and_are_independent():
    assert commute(AMOUNT, YEAR, REF, REF)
    assert compare(AMOUNT, YEAR, REF, REF) is Relation.INDEPENDENT


def test_two_words_of_one_paragraph_commute():
    assert compare(AMOUNT, VERB, REF, REF) is Relation.INDEPENDENT


def test_same_wording_twice_is_a_duplicate():
    assert compare(AMOUNT, AMOUNT_AGAIN, REF, REF) is Relation.DUPLICATE


def test_same_words_at_different_places_is_a_near_duplicate():
    text = Text(
        "T1",
        (
            Article(
                "3",
                ("Le chat dort.", "Le chat mange."),
            ),
        ),
    )
    ref = Version.of(text)

    def swap(number, line):
        body = f"<p>À l'alinéa {line}, substituer au mot :</p><p>« chat »</p>"
        body += "<p>le mot :</p><p>« chien ».</p>"
        return draft(text, Amendment(number, "ART. 3", body, id=number))

    assert compare(swap("N1", 1), swap("N2", 2), ref, ref) is Relation.NEAR_DUPLICATE


def test_different_values_for_one_word_conflict():
    assert compare(AMOUNT, OTHER_AMOUNT, REF, REF) is Relation.CONFLICT


def test_rewrite_against_inner_edit_conflicts():
    assert not commute(REWRITE, AMOUNT, REF, REF)
    assert compare(REWRITE, AMOUNT, REF, REF) is Relation.CONFLICT


def test_insertions_at_the_same_point_do_not_commute():
    assert not commute(INSERT_1, INSERT_2, REF, REF)
    assert compare(INSERT_1, INSERT_2, REF, REF) is Relation.CONFLICT


def test_an_amendment_refused_alone_is_raised():
    unreadable = amendment("Z", "Faire quelque chose d'incompréhensible.")
    with pytest.raises(Refusal) as error:
        compare(AMOUNT, unreadable, REF, REF)
    assert error.value.reason is Reason.OUT_OF_SCOPE


def test_comparison_on_a_later_version():
    later, _ = replay(REF, REF, AMOUNT)
    assert compare(VERB, YEAR, later, REF) is Relation.INDEPENDENT
    assert compare(VERB, substitute("A9", 1, "vendre", "céder"), later, REF) is Relation.DUPLICATE


def test_an_order_refused_means_no_commutation():
    """`REWRITE` puis `AMOUNT` : les mots cités ont disparu, `AMOUNT` ne s'applique plus."""
    assert replay(REF, REF, AMOUNT) and replay(REF, REF, REWRITE)
    assert not commute(AMOUNT, REWRITE, REF, REF)


def test_conflicting_splices_always_interfere_in_effects():
    drafts = [AMOUNT, VERB, YEAR, OTHER_AMOUNT, REWRITE, INSERT_1, INSERT_2]
    tree = REF.find("3")
    pairs = [
        (a, b)
        for a in drafts
        for b in drafts
        if a is not b and any(conflicts(x, y) for x in a.patch for y in b.patch)
    ]
    assert pairs
    for a, b in pairs:
        assert effect_of(tree, a.patch).interferes(effect_of(tree, b.patch))
