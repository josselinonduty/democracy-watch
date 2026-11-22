"""Paliers de tolérance : repérage, refus, trace, rejeu."""

import pytest

from engine import usecases
from engine.domain import tolerance, writing
from engine.domain.documents import Amendment, Article, Text
from engine.domain.refusal import Reason, Refusal
from engine.domain.tolerance import Tolerance
from engine.domain.version import Version
from engine.domain.writing import Anchor
from engine.usecases.draft import draft
from engine.usecases.replay import replay

T, A = Tolerance.TYPOGRAPHY, Tolerance.APPROXIMATE


def test_fold_maps_back_to_original_positions():
    folded, origin = tolerance.fold("a 4 000 € au-delà")
    assert folded == "a\x014000\x01€\x01au\x01delà"
    assert origin[folded.index("4000")] == 2 and origin[-1] == len("a 4 000 € au-delà")


@pytest.mark.parametrize(
    ("line", "cited", "span", "palier"),
    [
        ("une amende de 4 000 euros.", "4000 euros", (14, 25), T),
        ("une amende de 4000 euros.", "4 000 euros", (14, 24), T),
        ("au-delà du seuil", "au delà", (0, 7), T),
        ("au delà du seuil", "au-delà", (0, 7), T),
        ("le seuil – haut", "seuil - haut", (3, 15), T),
        ("le chat noir", "chat", (3, 7), None),  # exact : aucun palier
    ],
)
def test_typography(line, cited, span, palier):
    found = writing.locate([line], Anchor(cited))
    assert (found.start, found.end, found.tolerance) == (*span, palier)


def test_typography_keeps_whole_words():
    with pytest.raises(Refusal) as error:
        writing.locate(["le porte-parole"], Anchor("porte parole x"))
    assert error.value.reason is Reason.QUOTE_MISSING
    with pytest.raises(Refusal):
        writing.locate(["le porte-parole"], Anchor("le porte"))


def test_typography_accepts_an_explicit_occurrence():
    found = writing.locate(["4 000 puis 4 000"], Anchor("4000", -1))
    assert (found.start, found.tolerance) == (11, T)


def test_exact_multiple_is_not_softened():
    with pytest.raises(Refusal) as error:
        writing.locate(["la loi et la loi"], Anchor("la loi"))
    assert error.value.reason is Reason.QUOTE_MULTIPLE


def test_typo_is_found_with_a_trace():
    found = writing.locate(["le montant des amendes fixé"], Anchor("montnat des amendes"))
    assert found.tolerance is A
    assert (found.start, found.end) == (3, 22)


@pytest.mark.parametrize(
    "cited",
    [
        "montant des amendez",  # dernier caractère changé : un autre mot (pluriel, féminin…)
        "montant dse amnedes",  # deux mots fautifs
        "mnt des amendes",  # trop court / deux éditions
        "montant 4 00O",  # chiffre
        "montnat",  # un seul mot
        "mon des",  # citation trop courte
    ],
)
def test_typo_refused(cited):
    with pytest.raises(Refusal) as error:
        writing.locate(["le montant des amendes fixé"], Anchor(cited))
    assert error.value.reason is Reason.QUOTE_MISSING


def test_typo_needs_a_single_candidate():
    with pytest.raises(Refusal) as error:
        writing.locate(
            ["le montant des amendes, le montant des amendes"], Anchor("montnat des amendes")
        )
    assert "2 candidats" in error.value.detail


def test_typo_refused_with_explicit_occurrence():
    with pytest.raises(Refusal):
        writing.locate(["le montant des amendes"], Anchor("montnat des amendes", 1))


# Projection et rejeu

TEXT = Text("T0", (Article("3", ("Une amende de 4 000 euros est due.", "Le second alinéa.")),))


def amendment(number, *paragraphs):
    return Amendment(number, "ART. 3", "".join(f"<p>{p}</p>" for p in paragraphs), id=number)


def sub(old):
    return amendment(
        "CE1",
        "À l'alinéa 1, substituer au montant :",
        f"« {old} »",
        "le montant :",
        "« 10 000 euros ».",
    )


def test_projection_is_applied_and_traced():
    exact = usecases.project(TEXT, sub("4 000 euros"))
    tolerated = usecases.project(TEXT, sub("4000 euros"))
    assert not exact.tolerated and tolerated.tolerated
    assert tolerated.instructions[0].tolerance is T
    assert tolerated.status is exact.status
    assert tolerated.result == exact.result  # la tolérance ne compte pas dans la comparaison


def test_replay_keeps_a_tolerance_already_in_the_draft():
    reference = Version.of(TEXT)
    version, _ = replay(reference, reference, draft(TEXT, sub("4000 euros")))
    assert version.find("3").lines[0].startswith("Une amende de 10 000 euros")


def test_replay_refuses_a_tolerance_born_after_filing():
    """Les mots exacts au dépôt, retouchés par un amendement antérieur : cible disparue."""
    reference = Version.of(TEXT)
    earlier = amendment(
        "CE0", "À l'alinéa 1, substituer au mot :", "« 4 000 »", "le mot :", "« 4000 »."
    )
    version, _ = replay(reference, reference, draft(TEXT, earlier))
    with pytest.raises(Refusal) as error:
        replay(version, reference, draft(TEXT, sub("4 000 euros")))
    assert error.value.reason is Reason.TARGET_GONE


def test_explicit_rank_counts_typographic_variants():
    first = writing.locate(["4 000 puis 4000"], Anchor("4000", 1))
    last = writing.locate(["4000 puis 4 000"], Anchor("4000", -1))
    assert (first.start, first.tolerance) == (0, T)
    assert (last.start, last.tolerance) == (10, T)


def test_known_limits_are_acted():
    """Les paliers confondent des mots proches : c'est la trace qui prévient."""
    assert writing.locate(["peut-être"], Anchor("peut être")).tolerance is T
    assert writing.locate(["la maire de Lyon"], Anchor("la mairie de Lyon")).tolerance is A
