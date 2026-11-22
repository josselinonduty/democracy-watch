"""Statuts des non-adoptés : sort traduit par l'adaptateur, prédiction des tombés, ignorés."""

import dataclasses

from engine.adapters import tricoteuses as adapter
from engine.domain.documents import Amendment, Article, Outcome, Text
from engine.domain.status import Status
from engine.usecases import consolidate
from projection.datasources import tricoteuses as source

LINES = (
    "I. – Le fait de vendre ce produit est puni d'une amende de 4 000 euros.",
    "II. – Le présent article entre en vigueur le 1er janvier 2027.",
)
TEXT = Text("T0", (Article("3", LINES),))


def amendment(number, outcome, *paragraphs, label="ART. 3"):
    body = "".join(f"<p>{p}</p>" for p in paragraphs)
    return Amendment(number, label, body, id=number, outcome=outcome)


def substitute(number, outcome, line, old, new):
    return amendment(
        number,
        outcome,
        f"À l'alinéa {line}, substituer au mot :",
        f"« {old} »",
        "le mot :",
        f"« {new} ».",
    )


def insert(number, outcome, text):
    return amendment(number, outcome, "Après l'alinéa 1, insérer l'alinéa suivant :", f"« {text} »")


REWRITE = amendment("A1", Outcome.ADOPTED, "Rédiger ainsi l'alinéa 1 :", "« Alinéa réécrit. »")


def statuses(*amendments):
    return [p.status for p in consolidate(TEXT, amendments).projections]


def test_outcome_comes_from_the_source_sort():
    def outcome(sort):
        amendement = source.amendement_from({"uid": "A", "numeroLong": "1", "sortAmendement": sort})
        return adapter.amendment_from(amendement).outcome

    assert outcome("Adopté") is Outcome.ADOPTED
    assert outcome("Rejeté") is Outcome.REJECTED
    assert outcome("Tombé") is Outcome.FALLEN
    for sort in ("Retiré", "Non soutenu", "Irrecevable", "Irrecevable 40", "A discuter"):
        assert outcome(sort) is Outcome.NOT_VOTED
    assert outcome("Sort inventé") is None
    assert outcome(None) is None


def test_target_rewritten_by_an_earlier_adopted_amendment_is_predicted_fallen():
    rejected = substitute("A2", Outcome.REJECTED, 1, "vendre", "céder")
    assert statuses(REWRITE, rejected) == [Status.APPLIED, Status.PREDICTED_FALLEN]


def test_untouched_target_is_predicted_alive():
    rejected = substitute("A2", Outcome.REJECTED, 2, "2027", "2028")
    assert statuses(REWRITE, rejected) == [Status.APPLIED, Status.PREDICTED_ALIVE]


def test_only_earlier_adopted_amendments_count():
    rejected = substitute("A0", Outcome.FALLEN, 1, "vendre", "céder")
    assert statuses(rejected, REWRITE) == [Status.PREDICTED_ALIVE, Status.APPLIED]


def test_conflict_with_an_earlier_adopted_amendment_is_predicted_fallen():
    adopted = insert("A1", Outcome.ADOPTED, "Un.")
    rival = insert("A2", Outcome.REJECTED, "Deux.")
    assert statuses(adopted, rival) == [Status.APPLIED, Status.PREDICTED_FALLEN]


def test_independent_amendments_do_not_conflict():
    adopted = substitute("A1", Outcome.ADOPTED, 1, "vendre", "céder")
    other = substitute("A2", Outcome.REJECTED, 1, "4 000", "10 000")
    assert statuses(adopted, other) == [Status.APPLIED, Status.PREDICTED_ALIVE]


def test_not_understood_amendment_is_undetermined():
    outside = amendment("A2", Outcome.REJECTED, "Supprimer l'alinéa 1.", label="APRÈS ART. 3")
    unknown = amendment("A3", Outcome.REJECTED, "Que ce texte est beau.")
    assert statuses(REWRITE, outside, unknown) == [Status.APPLIED] + [Status.UNDETERMINED] * 2


def test_not_voted_amendment_is_ignored_without_reading_it():
    withdrawn = amendment("A2", Outcome.NOT_VOTED, "Que ce texte est beau.")
    (_, projection) = consolidate(TEXT, [REWRITE, withdrawn]).projections
    assert projection.status is Status.IGNORED
    assert projection.result is None
    assert projection.outcome is Outcome.NOT_VOTED


def test_unvoted_amendments_never_change_the_text_nor_block_the_article():
    rejected = substitute("A2", Outcome.REJECTED, 2, "2027", "2028")
    withdrawn = amendment("A3", Outcome.NOT_VOTED, "Supprimer l'alinéa 2.")
    alone = consolidate(TEXT, [REWRITE])
    mixed = consolidate(TEXT, [REWRITE, rejected, withdrawn])
    assert mixed.articles == alone.articles
    assert mixed.version.fingerprint() == alone.version.fingerprint()
    assert all(p.result is None for p in mixed.projections[1:])


def test_projections_keep_the_input_order_and_the_real_outcome():
    amendments = [
        substitute("A0", Outcome.REJECTED, 2, "2027", "2028"),
        REWRITE,
        amendment("A2", Outcome.NOT_VOTED, "x"),
        substitute("A3", Outcome.FALLEN, 1, "vendre", "céder"),
    ]
    projections = consolidate(TEXT, amendments).projections
    assert [p.amendment for p in projections] == ["A0", "A1", "A2", "A3"]
    assert [p.outcome for p in projections] == [
        Outcome.REJECTED,
        Outcome.ADOPTED,
        Outcome.NOT_VOTED,
        Outcome.FALLEN,
    ]


def test_unknown_outcome_keeps_the_previous_behaviour():
    legacy = amendment("A1", None, "Rédiger ainsi l'alinéa 1 :", "« Alinéa réécrit. »")
    assert statuses(legacy) == [Status.APPLIED]


def test_unread_earlier_adopted_amendment_makes_alive_undetermined():
    unread = amendment("A1", Outcome.ADOPTED, "Que ce texte est beau.")
    rejected = substitute("A2", Outcome.REJECTED, 2, "2027", "2028")
    assert statuses(unread, rejected) == [Status.NOT_PARSED, Status.UNDETERMINED]


def test_adopted_amendment_without_article_blinds_every_article():
    unknown = amendment("A1", Outcome.ADOPTED, "Supprimer l'alinéa 1.", label="ART. 3 À 5")
    rejected = substitute("A2", Outcome.REJECTED, 2, "2027", "2028")
    assert statuses(unknown, rejected)[1] is Status.UNDETERMINED


def test_unread_adopted_amendment_does_not_hide_a_certain_fall():
    unread = amendment("A1", Outcome.ADOPTED, "Que ce texte est beau.")
    rejected = substitute("A3", Outcome.REJECTED, 1, "vendre", "céder")
    assert statuses(REWRITE, unread, rejected)[2] is Status.PREDICTED_FALLEN


def test_unvoted_sub_amendment_is_undetermined():
    sub = amendment("A2", Outcome.REJECTED, "À l'alinéa 1, supprimer le mot :", "« ce »")
    sub = dataclasses.replace(sub, parent_id="A1")
    assert statuses(REWRITE, sub) == [Status.APPLIED, Status.UNDETERMINED]


def test_other_article_is_not_affected_by_unread_amendment():
    two = Text("T0", (Article("3", LINES), Article("4", ("Autre texte.",))))
    unread = amendment("A1", Outcome.ADOPTED, "Que ce texte est beau.", label="ART. 4")
    rejected = substitute("A2", Outcome.REJECTED, 2, "2027", "2028")
    result = consolidate(two, [unread, rejected])
    assert [p.status for p in result.projections] == [Status.NOT_PARSED, Status.PREDICTED_ALIVE]
