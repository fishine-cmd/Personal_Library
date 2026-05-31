"""Detect and remove unused dictionary entries.

Dictionary tables (authors / affiliations / publishers / sources / keywords / tags)
are shared globally across users. Records not referenced by any document or
author are dead weight and can be safely removed.

Duplicates (case-insensitive name collisions) are also surfaced for review —
we don't auto-merge because picking the canonical row and rewriting foreign
keys requires human judgment.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

from ..extensions import db
from ..models import Author, AuthorCode, Affiliation, Publisher, Source, Keyword, Tag


# ---- Orphan detection ----------------------------------------------------

def find_orphan_authors(user_id: int) -> list[Author]:
    return (
        Author.query.filter_by(user_id=user_id)
        .filter(~Author.document_links.any()).all()
    )


def find_orphan_affiliations(user_id: int) -> list[Affiliation]:
    return (
        Affiliation.query.filter_by(user_id=user_id)
        .filter(~Affiliation.authors.any()).all()
    )


def find_orphan_publishers(user_id: int) -> list[Publisher]:
    return (
        Publisher.query.filter_by(user_id=user_id)
        .filter(~Publisher.sources.any()).all()
    )


def find_orphan_sources(user_id: int) -> list[Source]:
    return (
        Source.query.filter_by(user_id=user_id)
        .filter(~Source.documents.any()).all()
    )


def find_orphan_keywords(user_id: int) -> list[Keyword]:
    return (
        Keyword.query.filter_by(user_id=user_id)
        .filter(~Keyword.documents.any()).all()
    )


def find_orphan_tags(user_id: int) -> list[Tag]:
    return (
        Tag.query.filter_by(user_id=user_id)
        .filter(~Tag.documents.any()).all()
    )


def scan_orphans(user_id: int) -> dict[str, list]:
    return {
        "authors": find_orphan_authors(user_id),
        "affiliations": find_orphan_affiliations(user_id),
        "publishers": find_orphan_publishers(user_id),
        "sources": find_orphan_sources(user_id),
        "keywords": find_orphan_keywords(user_id),
        "tags": find_orphan_tags(user_id),
    }


# ---- Orphan deletion -----------------------------------------------------

def delete_all_orphans(user_id: int) -> dict[str, int]:
    """Order matters: deleting sources frees publishers, deleting authors
    frees affiliations. We re-scan after each flush so cascading orphans
    surface naturally."""
    counts: dict[str, int] = {}

    sources = find_orphan_sources(user_id)
    for s in sources:
        db.session.delete(s)
    counts["sources"] = len(sources)
    db.session.flush()

    publishers = find_orphan_publishers(user_id)
    for p in publishers:
        db.session.delete(p)
    counts["publishers"] = len(publishers)
    db.session.flush()

    authors = find_orphan_authors(user_id)
    for a in authors:
        db.session.delete(a)
    counts["authors"] = len(authors)
    db.session.flush()

    affiliations = find_orphan_affiliations(user_id)
    for a in affiliations:
        db.session.delete(a)
    counts["affiliations"] = len(affiliations)
    db.session.flush()

    keywords = find_orphan_keywords(user_id)
    for k in keywords:
        db.session.delete(k)
    counts["keywords"] = len(keywords)
    db.session.flush()

    tags = find_orphan_tags(user_id)
    for t in tags:
        db.session.delete(t)
    counts["tags"] = len(tags)

    db.session.commit()
    return counts


# ---- Targeted pruning after a single-document delete ---------------------

def prune_orphans_around_document(
    authors: Iterable[Author],
    keywords: Iterable[Keyword],
    tags: Iterable[Tag],
    source: Optional[Source],
) -> dict[str, int]:
    """Check only the entities that were related to the just-deleted document.

    Caller passes the set/list of entities the document *was* referencing
    (collected before the delete). This function deletes any that now have
    zero references. ``affiliations`` are pruned transitively when their
    last author goes; ``publisher`` is pruned transitively when its last
    source goes; ``AuthorCode`` is pruned when a name has no remaining authors.
    Returns a count breakdown.
    """
    counts = {
        "keywords": 0,
        "tags": 0,
        "authors": 0,
        "affiliations": 0,
        "sources": 0,
        "publishers": 0,
        "author_codes": 0,
    }

    for kw in keywords:
        if not kw.documents:
            db.session.delete(kw)
            counts["keywords"] += 1

    for tag in tags:
        if not tag.documents:
            db.session.delete(tag)
            counts["tags"] += 1

    affs_to_check: set[Affiliation] = set()
    user_names_to_check: set[tuple[int, str]] = set()
    for a in authors:
        if not a.document_links:
            affs_to_check.update(a.affiliations)
            user_names_to_check.add((a.user_id, a.name))
            db.session.delete(a)
            counts["authors"] += 1

    db.session.flush()

    for aff in affs_to_check:
        if not aff.authors:
            db.session.delete(aff)
            counts["affiliations"] += 1

    for uid, name in user_names_to_check:
        if not Author.query.filter_by(user_id=uid, name=name).first():
            counter = db.session.get(AuthorCode, (uid, name))
            if counter is not None:
                db.session.delete(counter)
                counts["author_codes"] += 1

    publisher_to_check: Optional[Publisher] = None
    if source is not None and not source.documents:
        publisher_to_check = source.publisher
        db.session.delete(source)
        counts["sources"] += 1
        db.session.flush()

    if publisher_to_check is not None and not publisher_to_check.sources:
        db.session.delete(publisher_to_check)
        counts["publishers"] += 1

    return counts


# ---- Duplicate detection (display-only) ----------------------------------

_WS = re.compile(r"\s+")


def _normalize(name: str) -> str:
    return _WS.sub(" ", (name or "").strip().lower())


def _group_by_normalized_name(items: list) -> list[list]:
    buckets: dict[str, list] = {}
    for item in items:
        key = _normalize(item.name)
        if not key:
            continue
        buckets.setdefault(key, []).append(item)
    return [grp for grp in buckets.values() if len(grp) > 1]


def find_potential_duplicates(user_id: int) -> dict[str, list[list]]:
    def scoped(model):
        return model.query.filter_by(user_id=user_id).all()
    return {
        "authors": _group_by_normalized_name(scoped(Author)),
        "affiliations": _group_by_normalized_name(scoped(Affiliation)),
        "publishers": _group_by_normalized_name(scoped(Publisher)),
        "sources": _group_by_normalized_name(scoped(Source)),
        "keywords": _group_by_normalized_name(scoped(Keyword)),
        "tags": _group_by_normalized_name(scoped(Tag)),
    }
