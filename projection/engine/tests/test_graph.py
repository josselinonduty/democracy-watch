"""Rendu en graphe d'une consolidation."""

from engine.adapters.graph import render
from engine.domain.documents import Amendment, Article, Outcome, Text
from engine.usecases import consolidate

TEXT = Text(
    "PION1", (Article("3", ("Le premier alinéa.", "Le deuxième alinéa.", "Le troisième alinéa.")),)
)


def amendment(body, number):
    return Amendment(number, "ART. 3", f"<p>{body}</p>")


def test_single_amendment_is_a_linear_history():
    graph = render(consolidate(TEXT, [amendment("Supprimer l’alinéa 1.", "CE1")]))
    lines = graph.splitlines()
    assert lines[0] == "* base  article 3"
    assert lines[1].startswith("* ") and "(CE1)" in lines[1]
    assert lines[-1] == "*  résultat · 2 alinéa(s)"


def test_disjoint_amendments_fork_and_merge():
    graph = render(
        consolidate(
            TEXT,
            [amendment("Supprimer l’alinéa 1.", "CE1"), amendment("Supprimer l’alinéa 2.", "CE2")],
        )
    )
    lines = graph.splitlines()
    assert lines[1] == "|\\"
    assert lines[2].startswith("* |") and lines[3].startswith("| *")
    assert lines[4] == "|/"
    assert lines[-1] == "*  résultat · 1 alinéa(s)"


def test_conflict_is_marked_and_blocks_the_result():
    graph = render(
        consolidate(
            TEXT,
            [amendment("Supprimer l’alinéa 1.", "CE1"), amendment("Supprimer l’alinéa 1.", "CE2")],
        )
    )
    assert "x" in graph and "conflit" in graph
    assert graph.splitlines()[-1].startswith("o  non consolidé")


def test_oldest_wins_is_shown_with_dates_and_reason():
    old = Amendment(
        "CE1", "ART. 3", "<p>Supprimer l’alinéa 1.</p>", decided_at="2026-01-01T09:00:00"
    )
    new = Amendment(
        "CE2", "ART. 3", "<p>Supprimer l’alinéa 1.</p>", decided_at="2026-01-02T09:00:00"
    )
    lines = render(consolidate(TEXT, [new, old])).splitlines()
    kept = next(line for line in lines if "(CE1 · 2026-01-01)" in line)
    lost = next(line for line in lines if "(CE2 · 2026-01-02)" in line)
    assert kept.lstrip("*| ").startswith("(") and "x" not in kept.split("(")[0]
    assert "x" in lost.split("(")[0] and "décidé plus tôt" in lost


def test_amendment_without_article_is_listed_apart():
    other = Amendment("CE9", "ART. 3 À 5", "<p>Supprimer l’alinéa 1.</p>")
    assert "hors article" in render(consolidate(TEXT, [other]))


def test_render_leaves_out_amendments_that_were_not_voted():
    text = Text("T", (Article("3", ("Un mot.",)),))
    body = "<p>Rédiger ainsi l'alinéa 1 :</p><p>« Autre. »</p>"
    amendments = [
        Amendment("A1", "ART. 3", body, id="A1", outcome=Outcome.ADOPTED),
        Amendment("A2", "ART. 3", body, id="A2", outcome=Outcome.REJECTED),
        Amendment("A3", "ART. 3", body, id="A3", outcome=Outcome.NOT_VOTED),
    ]
    graph = render(consolidate(text, amendments))
    assert "A1" in graph and "A2" not in graph and "A3" not in graph
    assert "hors article" not in graph
