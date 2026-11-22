"""Consolidation de plusieurs amendements d'une même étape.

Contrat de l'appelant : `text` est le texte OFFICIEL d'entrée de l'étape (la base de la séance
est le texte adopté en commission, jamais notre résultat partiel) et `amendments` les amendements
qu'il a retenus (le moteur ne filtre pas sur le sort).

Le sort de l'amendement (`Amendment.outcome`) départage : adopté (ou inconnu), il est consolidé ;
rejeté ou tombé, il ne change jamais le texte et reçoit un statut prédit (`predict`) ; non voté, il
est `ignored`. Les amendements sont fournis dans l'ordre de la discussion : un non adopté est
confronté aux seuls adoptés qui le précèdent.

Chaque amendement est lu seul, comme dans `project`. Les amendements identiques sont fusionnés.
Les sous-amendements et leurs parents sont refusés, puis les patchs des amendements encore
applicables d'un même article sont confrontés par la politique de conflit (par défaut, la décision
la plus ancienne l'emporte). Les amendements applicables d'un article sont ensuite rejoués dans
l'ordre sur la version d'origine (`replay`) : le texte consolidé de l'article est lu dans cette
version. Il n'est fourni que si tous les amendements qui le visent sont appliqués : un amendement
refusé pourrait le modifier. Un amendement dont l'article visé est inconnu (`UNRESOLVED_ARTICLE`,
`article` None : absent, « ART. 3 À 5 »…) pourrait modifier n'importe quel article : tant qu'il
existe, aucun article n'est consolidé. Les « APRÈS ART. X » (`OUT_OF_SCOPE`) n'ont pas cet effet.
"""

import dataclasses
from collections.abc import Iterable

from engine.domain.documents import Amendment, Outcome, Text
from engine.domain.effect import Effect
from engine.domain.refusal import Reason, Refusal
from engine.domain.status import Status
from engine.domain.trace import Consolidation, Projection, Result
from engine.domain.tree import ArticleTree
from engine.domain.version import Version
from engine.reading import GRAMMAR_VERSION
from engine.usecases.draft import Draft, draft
from engine.usecases.merge import ConflictPolicy, oldest_wins
from engine.usecases.predict import predict
from engine.usecases.project import decide
from engine.usecases.replay import replay


def _reject_sub_amendments(drafts: list[Draft]) -> list[Draft]:
    """Refuse un sous-amendement et l'amendement qu'il modifie."""
    parents = {d.amendment.parent_id for d in drafts} - {None}
    refused = []
    for item in drafts:
        if item.amendment.parent_id is not None:
            item = item.refused(Refusal(Reason.OUT_OF_SCOPE, "sous-amendement"))
        elif item.amendment.id in parents:
            detail = "amendement ayant un sous-amendement"
            item = item.refused(Refusal(Reason.OUT_OF_SCOPE, detail))
        refused.append(item)
    return refused


def _twins(drafts: list[Draft]) -> dict[int, int]:
    """Pour chaque amendement identique à un précédent : l'indice du premier, qui le représente.

    Identiques : même série (`twin_group`), même article, même dispositif.
    """
    first_of: dict[tuple[str, str | None, tuple[str, ...]], int] = {}
    represented_by: dict[int, int] = {}
    for index, item in enumerate(drafts):
        group = item.amendment.twin_group
        if item.refusal is None and group is not None:
            first = first_of.setdefault((group, item.number, item.body), index)
            if first != index:
                represented_by[index] = first
    return represented_by


def _by_article(drafts: list[Draft], twins: dict[int, int]) -> dict[str, list[int]]:
    """Indices des brouillons applicables et non représentés, par numéro d'article."""
    groups: dict[str, list[int]] = {}
    for index, item in enumerate(drafts):
        if item.number is not None and index not in twins and item.applicable:
            groups.setdefault(item.number, []).append(index)
    return groups


def _article_result(tree: ArticleTree) -> Result:
    """Texte consolidé d'un article, lu dans sa version rejouée. Sans alinéa : article supprimé."""
    return Result(tree.number, tree.lines, not tree.paragraphs, tree.paragraphs)


def _unvoted(
    text: Text,
    amendments: tuple[Amendment, ...],
    voted: list[int],
    reference: Version,
    steps: dict[str, list[tuple[int, Draft, Version]]],
    unsettled: list[tuple[int, str | None]],
) -> dict[int, Projection]:
    """Projection de chaque non adopté, par rang d'entrée : un statut, jamais un résultat.

    `voted` : rangs des amendements consolidés ; `steps` : par article, les adoptés appliqués ;
    `unsettled` : rang et article des adoptés ni appliqués ni représentés par un jumeau. Un tel
    adopté a pu modifier le texte sans qu'on le sache : `predicted_alive` devient `undetermined`.
    """
    consolidated = set(voted)
    effects: dict[int, Effect | None] = {}

    def alone(rank: int, adopted: Draft) -> Effect | None:
        if rank not in effects:
            try:
                effects[rank] = replay(reference, reference, adopted)[1]
            except Refusal:
                effects[rank] = None
        return effects[rank]

    projections = {}
    for rank, amendment in enumerate(amendments):
        if rank in consolidated:
            continue
        if amendment.outcome is Outcome.NOT_VOTED:
            projections[rank] = Projection(
                amendment.number,
                None,
                None,
                None,
                "",
                (),
                GRAMMAR_VERSION,
                decided_at=amendment.decided_at,
                forced=Status.IGNORED,
                outcome=amendment.outcome,
            )
            continue
        item = draft(text, amendment)
        if amendment.parent_id is not None:  # son dispositif cite le texte de son parent
            status = Status.UNDETERMINED
            projections[rank] = dataclasses.replace(decide(item), result=None, forced=status)
            continue
        before = [s for s in steps.get(item.number or "", []) if s[0] < rank]
        current = before[-1][2] if before else reference
        known = [(d, e) for r, d, _ in before if (e := alone(r, d)) is not None]
        status = predict(item, current, reference, known)
        blind = any(r < rank and n in (None, item.number) for r, n in unsettled)
        if status is Status.PREDICTED_ALIVE and blind:
            status = Status.UNDETERMINED
        projections[rank] = dataclasses.replace(decide(item), result=None, forced=status)
    return projections


def _merged(
    voted: list[Projection], positions: list[int], unvoted: dict[int, Projection]
) -> list[Projection]:
    """Les projections des adoptés et des autres, dans l'ordre d'entrée."""
    by_rank = {**dict(zip(positions, voted, strict=True)), **unvoted}
    return [by_rank[rank] for rank in sorted(by_rank)]


def consolidate(
    text: Text, amendments: Iterable[Amendment], on_conflict: ConflictPolicy = oldest_wins
) -> Consolidation:
    """Projette `amendments` sur `text` : une projection par amendement, puis les articles."""
    everyone = tuple(amendments)
    positions = [i for i, a in enumerate(everyone) if a.outcome in (None, Outcome.ADOPTED)]
    amendments = tuple(everyone[i] for i in positions)
    drafts = _reject_sub_amendments([draft(text, amendment) for amendment in amendments])
    twins = _twins(drafts)
    groups = _by_article(drafts, twins)
    for indices in groups.values():
        for index, merged in zip(indices, on_conflict([drafts[i] for i in indices]), strict=True):
            drafts[index] = merged

    reference = Version.of(text)
    replayed: dict[str, Version] = {}
    steps: dict[str, list[tuple[int, Draft, Version]]] = {}  # adoptés appliqués : rang, version
    for number, indices in groups.items():
        current = reference
        for index in (i for i in indices if drafts[i].applicable):
            try:
                current, _ = replay(current, reference, drafts[index])
                steps.setdefault(number, []).append((positions[index], drafts[index], current))
            except Refusal as refusal:
                drafts[index] = drafts[index].refused(refusal)
        replayed[number] = current

    projections: list[Projection] = []
    for index, item in enumerate(drafts):
        if index in twins:  # le représentant est avant : sa projection existe déjà
            represented = projections[twins[index]]
            forced = Status.IDENTICAL if represented.applied else represented.forced
            same = dataclasses.replace(represented, amendment=item.amendment.number, forced=forced)
            projections.append(same)
        elif item.amendment.parent_id is not None:
            projections.append(dataclasses.replace(decide(item), forced=Status.SUB_AMENDMENT))
        else:
            projections.append(decide(item))

    # Cible inconnue : cet amendement pourrait modifier n'importe quel article.
    unlocated = any(
        p.reason is Reason.UNRESOLVED_ARTICLE and p.article is None for p in projections
    )
    articles = []
    version = reference
    for article in () if unlocated else text.articles:
        targeting = [p for p in projections if p.article == article.number]
        if targeting and all(p.applied for p in targeting):
            tree = replayed[article.number].find(article.number)
            articles.append(_article_result(tree))
            group = (drafts[i].amendment for i in groups[article.number])
            version = version.replace(tree, *(a.id or a.number for a in group))
    applied = {rank for lane in steps.values() for rank, _, _ in lane}
    represented = {positions[i] for i in twins}
    unsettled = [
        (positions[i], d.number)
        for i, d in enumerate(drafts)
        if positions[i] not in applied | represented
    ]
    unvoted = _unvoted(text, everyone, positions, reference, steps, unsettled)
    merged = _merged(projections, positions, unvoted)
    return Consolidation(tuple(merged), tuple(articles), version)
