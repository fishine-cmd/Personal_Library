"""Detect and remove unused dictionary entries.

Dictionary tables (authors / affiliations / publishers / sources / keywords)
are shared globally across users. Records not referenced by any document or
author are dead weight and can be safely removed.

Duplicates (case-insensitive name collisions) are also surfaced for review —
we don't auto-merge because picking the canonical row and rewriting foreign
keys requires human judgment.
"""

from __future__ import annotations

import re
import json
from copy import deepcopy
from typing import Iterable, Optional

from ..extensions import db
from ..models import (
    Author,
    AuthorAffiliation,
    AuthorCode,
    Affiliation,
    Document,
    DocumentAuthor,
    DocumentKeyword,
    Publisher,
    Source,
    Keyword,
    MergeAudit,
)


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


def scan_orphans(user_id: int) -> dict[str, list]:
    return {
        "authors": find_orphan_authors(user_id),
        "affiliations": find_orphan_affiliations(user_id),
        "publishers": find_orphan_publishers(user_id),
        "sources": find_orphan_sources(user_id),
        "keywords": find_orphan_keywords(user_id),
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

    db.session.commit()
    return counts


# ---- Targeted pruning after a single-document delete ---------------------

def prune_orphans_around_document(
    authors: Iterable[Author],
    keywords: Iterable[Keyword],
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
    }


# ---- Merge preview/apply/rollback ---------------------------------------


def _build_merge_plan(user_id: int) -> dict[str, list[dict]]:
    groups = find_potential_duplicates(user_id)
    plan: dict[str, list[dict]] = {
        "authors": [],
        "affiliations": [],
        "publishers": [],
        "sources": [],
        "keywords": [],
    }

    for group in groups["authors"]:
        ordered = sorted(group, key=lambda x: x.id)
        canonical = ordered[0]
        aliases = ordered[1:]
        impacted_docs = (
            db.session.query(DocumentAuthor.document_id)
            .filter(DocumentAuthor.author_id.in_([a.id for a in aliases]))
            .distinct()
            .count()
        )
        plan["authors"].append({
            "canonical_id": canonical.id,
            "canonical_name": canonical.name,
            "alias_ids": [a.id for a in aliases],
            "alias_names": [a.name for a in aliases],
            "impacted_docs": impacted_docs,
        })

    for group in groups["affiliations"]:
        ordered = sorted(group, key=lambda x: x.id)
        canonical = ordered[0]
        aliases = ordered[1:]
        impacted_authors = (
            db.session.query(AuthorAffiliation.author_id)
            .filter(AuthorAffiliation.affiliation_id.in_([a.id for a in aliases]))
            .distinct()
            .count()
        )
        plan["affiliations"].append({
            "canonical_id": canonical.id,
            "canonical_name": canonical.name,
            "alias_ids": [a.id for a in aliases],
            "alias_names": [a.name for a in aliases],
            "impacted_docs": impacted_authors,
        })

    for group in groups["publishers"]:
        ordered = sorted(group, key=lambda x: x.id)
        canonical = ordered[0]
        aliases = ordered[1:]
        impacted_docs = (
            db.session.query(Document.id)
            .join(Source, Document.source_id == Source.id)
            .filter(Source.publisher_id.in_([a.id for a in aliases]))
            .distinct()
            .count()
        )
        plan["publishers"].append({
            "canonical_id": canonical.id,
            "canonical_name": canonical.name,
            "alias_ids": [a.id for a in aliases],
            "alias_names": [a.name for a in aliases],
            "impacted_docs": impacted_docs,
        })

    # Source duplicates are merged only inside same source.type to avoid
    # collapsing legitimate journal/conference name collisions.
    by_norm_and_type: dict[tuple[str, str], list[Source]] = {}
    for src in Source.query.filter_by(user_id=user_id).all():
        by_norm_and_type.setdefault((_normalize(src.name), src.type), []).append(src)
    for _, typed_group in by_norm_and_type.items():
        if len(typed_group) < 2:
            continue
        ordered = sorted(typed_group, key=lambda x: x.id)
        canonical = ordered[0]
        aliases = ordered[1:]
        impacted_docs = (
            db.session.query(Document.id)
            .filter(Document.source_id.in_([a.id for a in aliases]))
            .distinct()
            .count()
        )
        plan["sources"].append({
            "canonical_id": canonical.id,
            "canonical_name": canonical.name,
            "alias_ids": [a.id for a in aliases],
            "alias_names": [a.name for a in aliases],
            "impacted_docs": impacted_docs,
            "source_type": canonical.type,
        })

    for group in groups["keywords"]:
        ordered = sorted(group, key=lambda x: x.id)
        canonical = ordered[0]
        aliases = ordered[1:]
        impacted_docs = (
            db.session.query(DocumentKeyword.document_id)
            .filter(DocumentKeyword.keyword_id.in_([a.id for a in aliases]))
            .distinct()
            .count()
        )
        plan["keywords"].append({
            "canonical_id": canonical.id,
            "canonical_name": canonical.name,
            "alias_ids": [a.id for a in aliases],
            "alias_names": [a.name for a in aliases],
            "impacted_docs": impacted_docs,
        })
    return plan


def merge_preview(user_id: int) -> dict:
    plan = _build_merge_plan(user_id)
    return {
        "plan": plan,
        "summary": {
            "groups": sum(len(v) for v in plan.values()),
            "aliases": sum(len(g["alias_ids"]) for v in plan.values() for g in v),
            "impacted_docs": sum(g["impacted_docs"] for v in plan.values() for g in v),
        },
    }


def _apply_author_group(canonical_id: int, alias_ids: list[int], audit: dict) -> int:
    changed = 0
    for alias_id in alias_ids:
        alias_links = DocumentAuthor.query.filter_by(author_id=alias_id).all()
        for link in alias_links:
            existing = DocumentAuthor.query.filter_by(
                document_id=link.document_id, author_id=canonical_id
            ).first()
            if existing:
                audit["doc_author_deleted"].append({"document_id": link.document_id, "author_id": alias_id, "author_order": link.author_order})
                db.session.delete(link)
                changed += 1
            else:
                audit["doc_author_updates"].append({"document_id": link.document_id, "from_author_id": alias_id, "to_author_id": canonical_id})
                link.author_id = canonical_id
                changed += 1

        aff_links = AuthorAffiliation.query.filter_by(author_id=alias_id).all()
        for al in aff_links:
            exists_aff = AuthorAffiliation.query.filter_by(author_id=canonical_id, affiliation_id=al.affiliation_id).first()
            if exists_aff:
                audit["author_aff_deleted"].append({"author_id": alias_id, "affiliation_id": al.affiliation_id})
                db.session.delete(al)
            else:
                audit["author_aff_updates"].append({"from_author_id": alias_id, "to_author_id": canonical_id, "affiliation_id": al.affiliation_id})
                al.author_id = canonical_id

        alias_obj = db.session.get(Author, alias_id)
        if alias_obj is not None:
            audit["deleted"].append({"model": "author", "id": alias_obj.id, "payload": {"name": alias_obj.name, "code": alias_obj.code}})
            db.session.delete(alias_obj)
    return changed


def _apply_affiliation_group(canonical_id: int, alias_ids: list[int], audit: dict) -> int:
    changed = 0
    for alias_id in alias_ids:
        links = AuthorAffiliation.query.filter_by(affiliation_id=alias_id).all()
        for link in links:
            exists = AuthorAffiliation.query.filter_by(author_id=link.author_id, affiliation_id=canonical_id).first()
            if exists:
                audit["author_aff_deleted"].append({"author_id": link.author_id, "affiliation_id": alias_id})
                db.session.delete(link)
            else:
                audit["author_aff_updates"].append({"author_id": link.author_id, "from_affiliation_id": alias_id, "to_affiliation_id": canonical_id})
                link.affiliation_id = canonical_id
            changed += 1
        obj = db.session.get(Affiliation, alias_id)
        if obj is not None:
            audit["deleted"].append({"model": "affiliation", "id": obj.id, "payload": {"name": obj.name}})
            db.session.delete(obj)
    return changed


def _apply_publisher_group(canonical_id: int, alias_ids: list[int], audit: dict) -> int:
    changed = 0
    for alias_id in alias_ids:
        sources = Source.query.filter_by(publisher_id=alias_id).all()
        for src in sources:
            audit["source_publisher_updates"].append({"source_id": src.id, "from_publisher_id": alias_id, "to_publisher_id": canonical_id})
            src.publisher_id = canonical_id
            changed += 1
        obj = db.session.get(Publisher, alias_id)
        if obj is not None:
            audit["deleted"].append({"model": "publisher", "id": obj.id, "payload": {"name": obj.name}})
            db.session.delete(obj)
    return changed


def _apply_source_group(canonical_id: int, alias_ids: list[int], audit: dict) -> int:
    changed = 0
    for alias_id in alias_ids:
        docs = Document.query.filter_by(source_id=alias_id).all()
        for d in docs:
            audit["doc_source_updates"].append({"document_id": d.id, "from_source_id": alias_id, "to_source_id": canonical_id})
            d.source_id = canonical_id
            changed += 1
        obj = db.session.get(Source, alias_id)
        if obj is not None:
            audit["deleted"].append({"model": "source", "id": obj.id, "payload": {"name": obj.name, "type": obj.type, "publisher_id": obj.publisher_id}})
            db.session.delete(obj)
    return changed


def _apply_keyword_group(canonical_id: int, alias_ids: list[int], audit: dict) -> int:
    changed = 0
    for alias_id in alias_ids:
        links = DocumentKeyword.query.filter_by(keyword_id=alias_id).all()
        for link in links:
            exists = DocumentKeyword.query.filter_by(document_id=link.document_id, keyword_id=canonical_id).first()
            if exists:
                audit["doc_keyword_deleted"].append({"document_id": link.document_id, "keyword_id": alias_id})
                db.session.delete(link)
            else:
                audit["doc_keyword_updates"].append({"document_id": link.document_id, "from_keyword_id": alias_id, "to_keyword_id": canonical_id})
                link.keyword_id = canonical_id
            changed += 1
        obj = db.session.get(Keyword, alias_id)
        if obj is not None:
            audit["deleted"].append({"model": "keyword", "id": obj.id, "payload": {"name": obj.name}})
            db.session.delete(obj)
    return changed


def merge_apply(user_id: int) -> dict:
    plan = _build_merge_plan(user_id)
    audit = {
        "user_id": user_id,
        "plan": deepcopy(plan),
        "deleted": [],
        "doc_author_updates": [],
        "doc_author_deleted": [],
        "author_aff_updates": [],
        "author_aff_deleted": [],
        "source_publisher_updates": [],
        "doc_source_updates": [],
        "doc_keyword_updates": [],
        "doc_keyword_deleted": [],
    }
    affected = 0
    for g in plan["authors"]:
        affected += _apply_author_group(g["canonical_id"], g["alias_ids"], audit)
    for g in plan["affiliations"]:
        affected += _apply_affiliation_group(g["canonical_id"], g["alias_ids"], audit)
    for g in plan["publishers"]:
        affected += _apply_publisher_group(g["canonical_id"], g["alias_ids"], audit)
    for g in plan["sources"]:
        affected += _apply_source_group(g["canonical_id"], g["alias_ids"], audit)
    for g in plan["keywords"]:
        affected += _apply_keyword_group(g["canonical_id"], g["alias_ids"], audit)

    summary = {
        "groups_merged": sum(len(v) for v in plan.values()),
        "aliases_merged": sum(len(g["alias_ids"]) for v in plan.values() for g in v),
        "records_relinked": affected,
    }
    audit_row = MergeAudit(
        user_id=user_id,
        action="merge_apply",
        summary_json=json.dumps(summary, ensure_ascii=False),
        payload_json=json.dumps(audit, ensure_ascii=False),
    )
    db.session.add(audit_row)
    db.session.commit()
    return {
        "ok": True,
        **summary,
        "audit_id": audit_row.id,
    }


def _rollback_from_audit_row(user_id: int, row: MergeAudit) -> dict:
    audit = json.loads(row.payload_json or "{}")
    if not audit:
        return {"ok": False, "error": "invalid_audit_payload"}

    # Restore deleted dictionary rows first.
    for d in audit["deleted"]:
        model = d["model"]
        payload = d["payload"]
        if model == "author":
            obj = Author(id=d["id"], user_id=user_id, name=payload["name"], code=payload["code"])
        elif model == "affiliation":
            obj = Affiliation(id=d["id"], user_id=user_id, name=payload["name"])
        elif model == "publisher":
            obj = Publisher(id=d["id"], user_id=user_id, name=payload["name"])
        elif model == "source":
            obj = Source(
                id=d["id"], user_id=user_id, name=payload["name"],
                type=payload["type"], publisher_id=payload["publisher_id"]
            )
        elif model == "keyword":
            obj = Keyword(id=d["id"], user_id=user_id, name=payload["name"])
        else:
            continue
        db.session.merge(obj)
    db.session.flush()

    for ch in audit["doc_source_updates"]:
        doc = db.session.get(Document, ch["document_id"])
        if doc is not None:
            doc.source_id = ch["from_source_id"]

    for ch in audit["source_publisher_updates"]:
        src = db.session.get(Source, ch["source_id"])
        if src is not None:
            src.publisher_id = ch["from_publisher_id"]

    for ch in audit["doc_keyword_updates"]:
        link = DocumentKeyword.query.filter_by(document_id=ch["document_id"], keyword_id=ch["to_keyword_id"]).first()
        if link is not None:
            link.keyword_id = ch["from_keyword_id"]
    for ch in audit["doc_keyword_deleted"]:
        exists = DocumentKeyword.query.filter_by(document_id=ch["document_id"], keyword_id=ch["keyword_id"]).first()
        if not exists:
            db.session.add(DocumentKeyword(document_id=ch["document_id"], keyword_id=ch["keyword_id"]))

    for ch in audit["author_aff_updates"]:
        if "from_affiliation_id" in ch:
            link = AuthorAffiliation.query.filter_by(author_id=ch["author_id"], affiliation_id=ch["to_affiliation_id"]).first()
            if link is not None:
                link.affiliation_id = ch["from_affiliation_id"]
        else:
            link = AuthorAffiliation.query.filter_by(author_id=ch["to_author_id"], affiliation_id=ch["affiliation_id"]).first()
            if link is not None:
                link.author_id = ch["from_author_id"]
    for ch in audit["author_aff_deleted"]:
        exists = AuthorAffiliation.query.filter_by(author_id=ch["author_id"], affiliation_id=ch["affiliation_id"]).first()
        if not exists:
            db.session.add(AuthorAffiliation(author_id=ch["author_id"], affiliation_id=ch["affiliation_id"]))

    for ch in audit["doc_author_updates"]:
        link = DocumentAuthor.query.filter_by(document_id=ch["document_id"], author_id=ch["to_author_id"]).first()
        if link is not None:
            link.author_id = ch["from_author_id"]
    for ch in audit["doc_author_deleted"]:
        exists = DocumentAuthor.query.filter_by(document_id=ch["document_id"], author_id=ch["author_id"]).first()
        if not exists:
            db.session.add(DocumentAuthor(document_id=ch["document_id"], author_id=ch["author_id"], author_order=ch["author_order"]))

    row.rolled_back_at = db.func.now()
    rollback_summary = {"rollback_of": row.id}
    rb_row = MergeAudit(
        user_id=user_id,
        action="merge_rollback",
        target_audit_id=row.id,
        summary_json=json.dumps(rollback_summary, ensure_ascii=False),
        payload_json=json.dumps({"target_audit_id": row.id}, ensure_ascii=False),
    )
    db.session.add(rb_row)
    db.session.commit()
    return {"ok": True, "rolled_back_audit_id": row.id, "rollback_audit_id": rb_row.id}


def merge_rollback_last(user_id: int) -> dict:
    row = (
        MergeAudit.query.filter_by(user_id=user_id, action="merge_apply", rolled_back_at=None)
        .order_by(MergeAudit.id.desc())
        .first()
    )
    if not row:
        return {"ok": False, "error": "no_last_merge"}
    return _rollback_from_audit_row(user_id, row)


def merge_rollback_by_audit_id(user_id: int, audit_id: int) -> dict:
    row = MergeAudit.query.filter_by(
        id=audit_id, user_id=user_id, action="merge_apply"
    ).first()
    if not row:
        return {"ok": False, "error": "audit_not_found"}
    if row.rolled_back_at is not None:
        return {"ok": False, "error": "already_rolled_back"}
    return _rollback_from_audit_row(user_id, row)


def list_merge_audits(user_id: int, limit: int = 20) -> list[dict]:
    rows = (
        MergeAudit.query.filter_by(user_id=user_id)
        .order_by(MergeAudit.id.desc())
        .limit(max(1, min(limit, 100)))
        .all()
    )
    out = []
    for r in rows:
        try:
            summary = json.loads(r.summary_json or "{}")
        except Exception:
            summary = {}
        out.append({
            "id": r.id,
            "action": r.action,
            "target_audit_id": r.target_audit_id,
            "rolled_back_at": r.rolled_back_at.isoformat() if r.rolled_back_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "summary": summary,
        })
    return out
