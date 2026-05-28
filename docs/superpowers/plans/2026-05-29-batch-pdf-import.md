# 批量 PDF 识别 + 批量 BibTeX 入库 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户能一次性上传 N (≤20) 个 PDF，对照 MinerU 解析的 markdown 逐篇填写 .bib，然后批量入库为带 PDF 附件的文献。

**Architecture:** 服务端无状态、三个单篇粒度端点（GET 页面、POST 识别一篇、POST 入库一篇），批次概念完全前端化。复用 `mineru_client`、重构 `bibtex_io` 抽出 `parse_entries` / `import_single_entry`，从 `documents.py` 抽出 `save_uploaded_files` 到 `services/file_io.py` 跨 Blueprint 共享。

**Tech Stack:** Flask + Flask-Login + SQLAlchemy + bibtexparser（后端）；vanilla JS + localStorage + marked.js（前端）；pytest + sqlite in-memory（测试）。

**Spec:** `docs/superpowers/specs/2026-05-29-batch-pdf-import-design.md`

---

## 任务总览

| # | 任务 | 类型 | 测试 |
|---|---|---|---|
| 1 | 添加测试基础设施 fixtures | 重构/基建 | 间接 |
| 2 | 抽离 `save_uploaded_files` 到 `services/file_io.py` | 重构 | TDD |
| 3 | `bibtex_io` 抽出 `parse_entries` | 重构 | TDD |
| 4 | `bibtex_io` 抽出 `import_single_entry`（含 `category_id`） | 重构 | TDD |
| 5 | `batch_bibtex` Blueprint 骨架 + GET 页面 + 注册 | 新增 | TDD |
| 6 | POST `/bibtex/batch/recognize` | 新增 | TDD |
| 7 | POST `/bibtex/batch/import`（含孤儿附件清理） | 新增 | TDD |
| 8 | 文献列表页加入口按钮 | UI | 手工 |
| 9 | `batch.html` 完整模板 + marked.js 资源 | UI | 手工 |
| 10 | 前端：识别队列状态机 | JS | 手工 |
| 11 | 前端：`.bib` 填写 + localStorage 草稿 + beforeunload | JS | 手工 |
| 12 | 前端：提交队列 + 结果汇总 | JS | 手工 |
| 13 | 前端：MinerU 健康预检 + 长 markdown 兜底 | JS | 手工 |
| 14 | 端到端手工验证清单 | 验收 | 手工 |

---

## Task 1: 添加测试基础设施 fixtures

**Files:**
- Modify: `tests/conftest.py`

加 4 个 fixture：`login_client`（已登录的 test client）、`seeded_user_id`（一个已注册用户的 ID）、`tiny_pdf_bytes`（最小可解析的 PDF 字节）、`mock_mineru`（patch `mineru_client.parse_pdf`）。后续所有测试任务都依赖这些。

- [ ] **Step 1: 改写 `tests/conftest.py`**

```python
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import User  # noqa: E402


@pytest.fixture
def app():
    app = create_app("test")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def user(app):
    with app.app_context():
        u = User(username="tester", email="t@example.com")
        u.set_password("pw123456")
        db.session.add(u)
        db.session.commit()
        return u.id


@pytest.fixture
def login_client(client):
    """Test client that has registered + logged in a user. Username 'tester'."""
    client.post(
        "/auth/register",
        data={"username": "tester", "password": "pw123456", "password2": "pw123456"},
    )
    return client


@pytest.fixture
def seeded_user_id(app, login_client):
    """Return the id of the user logged in via login_client."""
    with app.app_context():
        u = User.query.filter_by(username="tester").first()
        return u.id


# A minimal valid PDF (5 lines, "Hello World" via Tj) — enough for upload
# validation paths; not meaningful for MinerU parsing (use mock_mineru).
_TINY_PDF = (
    b"%PDF-1.1\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f \n"
    b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n0\n%%EOF\n"
)


@pytest.fixture
def tiny_pdf_bytes():
    return _TINY_PDF


@pytest.fixture
def upload_pdf(tiny_pdf_bytes):
    """Build (BytesIO, filename) tuple ready for Werkzeug test client uploads."""
    def _make(filename="sample.pdf"):
        return (io.BytesIO(tiny_pdf_bytes), filename)
    return _make


@pytest.fixture
def mock_mineru(monkeypatch):
    """Patch mineru_client.parse_pdf to return a fixed payload. Returns the
    list of calls so tests can assert request shape."""
    calls = []

    def fake_parse_pdf(base_url, file_bytes, filename, **kwargs):
        calls.append({"url": base_url, "filename": filename, "kwargs": kwargs})
        return {"md": f"# {filename}\n\nFake markdown body.", "content_list": []}

    from app.services import mineru_client
    monkeypatch.setattr(mineru_client, "parse_pdf", fake_parse_pdf)
    return calls
```

- [ ] **Step 2: 跑现有测试套件确认未破坏**

Run: `cd "D:\GitHub项目\Personal_Library" && python -m pytest tests -v`
Expected: 所有现有用例 PASS（新增 fixture 没人引用，所以不会被自动收集运行）。

- [ ] **Step 3: 提交**

```bash
git add tests/conftest.py
git commit -m "test: 新增 login_client/upload_pdf/mock_mineru 等批量功能测试夹具"
```

---

## Task 2: 抽离 `save_uploaded_files` 到 `services/file_io.py`

**Files:**
- Create: `app/services/file_io.py`
- Modify: `app/blueprints/documents.py:81-104`
- Test: `tests/test_file_io.py`

新函数签名 `save_uploaded_files(document, files, user_id) -> (saved_paths: list[Path], skipped_names: list[str])`。原 `documents._save_uploaded_files` 改为薄包装（仍把 skipped_names flash 出去），其余调用站不变。

- [ ] **Step 1: 写失败测试 `tests/test_file_io.py`**

```python
import io
from pathlib import Path

from werkzeug.datastructures import FileStorage

from app.extensions import db
from app.models import User, Document, File
from app.services.file_io import save_uploaded_files


def _make_filestorage(name="sample.pdf", content=b"%PDF-1.1\n%dummy\n"):
    return FileStorage(stream=io.BytesIO(content), filename=name, content_type="application/pdf")


def test_save_uploaded_files_creates_file_record_and_writes_disk(app):
    with app.app_context():
        u = User(username="u1", email="u1@x.com")
        u.set_password("pw123456")
        db.session.add(u)
        db.session.flush()
        doc = Document(user_id=u.id, title="T")
        db.session.add(doc)
        db.session.flush()

        fs = _make_filestorage("a.pdf", b"%PDF-1.1\nhello\n")
        saved, skipped = save_uploaded_files(doc, [fs], u.id)
        db.session.commit()

        assert len(saved) == 1
        assert saved[0].exists()
        assert skipped == []
        recs = File.query.filter_by(document_id=doc.id).all()
        assert len(recs) == 1
        assert recs[0].original_name == "a.pdf"
        assert recs[0].mime_type == "application/pdf"


def test_save_uploaded_files_skips_disallowed_extension(app):
    with app.app_context():
        u = User(username="u2", email="u2@x.com")
        u.set_password("pw123456")
        db.session.add(u)
        db.session.flush()
        doc = Document(user_id=u.id, title="T")
        db.session.add(doc)
        db.session.flush()

        fs = _make_filestorage("notes.exe", b"MZ\x90\x00")
        saved, skipped = save_uploaded_files(doc, [fs], u.id)

        assert saved == []
        assert skipped == ["notes.exe"]
        assert File.query.count() == 0


def test_save_uploaded_files_skips_empty_filename(app):
    with app.app_context():
        u = User(username="u3", email="u3@x.com")
        u.set_password("pw123456")
        db.session.add(u)
        db.session.flush()
        doc = Document(user_id=u.id, title="T")
        db.session.add(doc)
        db.session.flush()

        fs = _make_filestorage("", b"")
        saved, skipped = save_uploaded_files(doc, [fs], u.id)

        assert saved == []
        assert skipped == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_file_io.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.file_io'`

- [ ] **Step 3: 创建 `app/services/file_io.py`**

```python
"""共享附件保存工具。供 documents 与 batch_bibtex Blueprint 使用。

差异于历史 documents._save_uploaded_files 的点：
- 接 user_id 参数，不再隐式依赖 current_user，便于服务层重用与单测
- 不调用 flash；不允许的扩展名静默收集到 skipped_names 返回，让调用方决定提示方式
- 返回 (saved_paths, skipped_names)，让调用方在 commit 失败时回滚已写盘的文件
- 不 commit，由调用方掌控事务边界
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Iterable

from flask import current_app
from werkzeug.utils import secure_filename

from ..extensions import db
from ..models import File, Document


def save_uploaded_files(
    document: Document, files: Iterable, user_id: int
) -> tuple[list[Path], list[str]]:
    """Persist uploaded files to disk and add File rows to the session.

    Returns:
        (saved_paths, skipped_names)
        - saved_paths: absolute Paths actually written (so callers can unlink
          them on rollback)
        - skipped_names: original filenames rejected because of extension
    """
    upload_root = Path(current_app.config["UPLOAD_FOLDER"])
    allowed = current_app.config["ALLOWED_EXTENSIONS"]
    user_dir = upload_root / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    saved: list[Path] = []
    skipped: list[str] = []
    for f in files:
        if not f or not f.filename:
            continue
        ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
        if ext not in allowed:
            skipped.append(f.filename)
            continue
        original = secure_filename(f.filename) or "file"
        stored = f"{uuid.uuid4().hex}.{ext}"
        target = user_dir / stored
        f.save(target)
        saved.append(target)
        db.session.add(
            File(
                document_id=document.id,
                file_path=str(Path(str(user_id)) / stored).replace("\\", "/"),
                original_name=original,
                file_size=target.stat().st_size,
                mime_type=f.mimetype or "",
            )
        )
    return saved, skipped
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_file_io.py -v`
Expected: 3 PASS

- [ ] **Step 5: 把 `documents.py` 改为调用新模块**

替换 `app/blueprints/documents.py` 中第 81-104 行的 `_save_uploaded_files` 函数：

```python
from ..services.file_io import save_uploaded_files as _save_uploaded_files_impl


def _save_uploaded_files(document: Document, files):
    """Documents-blueprint wrapper that flashes a warning for skipped files."""
    _, skipped = _save_uploaded_files_impl(document, files, current_user.id)
    for name in skipped:
        flash(f"跳过不允许的文件类型: {name}", "warning")
```

确保旧函数 `_save_uploaded_files` 仍能被 `_persist_document_form` 调用（行 263、288）；不修改这两处调用站。

- [ ] **Step 6: 跑全部测试**

Run: `python -m pytest tests -v`
Expected: 之前的 `test_document_crud` 与新加的 file_io 测试均 PASS。

- [ ] **Step 7: 提交**

```bash
git add app/services/file_io.py app/blueprints/documents.py tests/test_file_io.py
git commit -m "refactor: 抽出 save_uploaded_files 到 services/file_io 供跨 Blueprint 复用"
```

---

## Task 3: `bibtex_io` 抽出 `parse_entries`

**Files:**
- Modify: `app/services/bibtex_io.py`
- Test: `tests/test_bibtex_io.py`

把 `import_bibtex` 里"解析 .bib 文本→拿到 entries 列表"那一步抽成纯函数。`import_bibtex` 此步骤改为调 `parse_entries`，行为不变。

- [ ] **Step 1: 写失败测试 `tests/test_bibtex_io.py`**

```python
import pytest

from app.services.bibtex_io import parse_entries


def test_parse_entries_single():
    text = "@article{key1, title={Foo}, year={2020}, author={Alice}}"
    entries = parse_entries(text)
    assert len(entries) == 1
    assert entries[0]["title"].strip("{}") == "Foo"


def test_parse_entries_empty():
    assert parse_entries("") == []
    assert parse_entries("   \n  ") == []


def test_parse_entries_multi():
    text = """
    @article{a, title={A}, year={2020}}
    @inproceedings{b, title={B}, year={2021}}
    """
    entries = parse_entries(text)
    assert len(entries) == 2
    assert {e["ENTRYTYPE"] for e in entries} == {"article", "inproceedings"}
```

注：故意不写 `test_parse_entries_malformed`——`bibtexparser` 对许多类型的格式错误表现为"返回更少 entry"而非抛异常，写死断言反而脆。让运行时错误自然冒泡即可。

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_bibtex_io.py -v`
Expected: FAIL with ImportError 或 AttributeError on `parse_entries`

- [ ] **Step 3: 修改 `app/services/bibtex_io.py`**

在文件顶部 imports 之后插入：

```python
def parse_entries(bib_text: str) -> list[dict]:
    """Parse .bib text into a list of entry dicts. No side effects.

    Returns empty list for blank input. Format errors from bibtexparser
    propagate as exceptions for the caller to surface.
    """
    if not bib_text or not bib_text.strip():
        return []
    parser = bibtexparser.bparser.BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False
    bib_db = bibtexparser.loads(bib_text, parser=parser)
    return bib_db.entries
```

把 `import_bibtex` 函数最开始的三行（构造 parser + loads）改为：

```python
def import_bibtex(bib_text: str, user_id: int) -> Tuple[int, int]:
    """Parse a .bib string and create Documents. Returns (created, skipped)."""
    entries = parse_entries(bib_text)

    created = 0
    skipped = 0
    for entry in entries:
        ...
```

（其余循环体不变。）

- [ ] **Step 4: 跑测试**

Run: `python -m pytest tests/test_bibtex_io.py tests/test_routes.py -v`
Expected: 新加的 3 个 parse 测试 PASS；旧的 `test_document_crud` 不受影响 PASS。

- [ ] **Step 5: 提交**

```bash
git add app/services/bibtex_io.py tests/test_bibtex_io.py
git commit -m "refactor(bibtex_io): 抽出 parse_entries 纯解析函数"
```

---

## Task 4: `bibtex_io` 抽出 `import_single_entry`（含 `category_id`）

**Files:**
- Modify: `app/services/bibtex_io.py`
- Test: `tests/test_bibtex_io.py`

把 `import_bibtex` 循环体抽成 `import_single_entry(entry, user_id, category_id=None) -> dict`，返回 `{"created": Document|None, "skipped_reason": str|None}`。原 `import_bibtex` 改为薄循环 + 末尾 commit，行为保持 100% 一致。

- [ ] **Step 1: 在 `tests/test_bibtex_io.py` 追加失败测试**

```python
from app.extensions import db
from app.models import User, Document, Category
from app.services.bibtex_io import import_single_entry, import_bibtex, parse_entries


def _seed_user(app, username="u_imp"):
    with app.app_context():
        u = User(username=username, email=f"{username}@x.com")
        u.set_password("pw123456")
        db.session.add(u)
        db.session.commit()
        return u.id


def test_import_single_entry_creates_document(app):
    uid = _seed_user(app, "u_create")
    with app.app_context():
        entry = parse_entries(
            "@article{k, title={Paper One}, year={2021}, author={Alice and Bob}, "
            "journal={Nature}, doi={10.1/abc}}"
        )[0]
        result = import_single_entry(entry, uid)
        db.session.commit()
        assert result["created"] is not None
        assert result["skipped_reason"] is None
        assert result["created"].title == "Paper One"
        assert result["created"].publication_year == 2021
        assert result["created"].doi == "10.1/abc"
        assert [a.name for a in result["created"].authors] == ["Alice", "Bob"]
        assert result["created"].source.name == "Nature"


def test_import_single_entry_skips_when_no_title(app):
    uid = _seed_user(app, "u_notitle")
    with app.app_context():
        entry = {"ENTRYTYPE": "article", "ID": "k", "title": "", "year": "2021"}
        result = import_single_entry(entry, uid)
        assert result["created"] is None
        assert result["skipped_reason"] is not None
        assert "title" in result["skipped_reason"].lower() or "标题" in result["skipped_reason"]


def test_import_single_entry_skips_duplicate_by_doi(app):
    uid = _seed_user(app, "u_doi")
    with app.app_context():
        existing = Document(user_id=uid, title="Existing", doi="10.1/dup")
        db.session.add(existing)
        db.session.commit()
        entry = parse_entries(
            "@article{k, title={Different Title}, year={2021}, doi={10.1/dup}}"
        )[0]
        result = import_single_entry(entry, uid)
        assert result["created"] is None
        assert result["skipped_reason"] is not None
        assert str(existing.id) in result["skipped_reason"]


def test_import_single_entry_skips_duplicate_by_title_year(app):
    uid = _seed_user(app, "u_ty")
    with app.app_context():
        existing = Document(user_id=uid, title="Same Title", publication_year=2020)
        db.session.add(existing)
        db.session.commit()
        entry = parse_entries(
            "@article{k, title={Same Title}, year={2020}}"
        )[0]
        result = import_single_entry(entry, uid)
        assert result["created"] is None
        assert result["skipped_reason"] is not None


def test_import_single_entry_with_category(app):
    uid = _seed_user(app, "u_cat")
    with app.app_context():
        cat = Category(user_id=uid, name="ML")
        db.session.add(cat)
        db.session.commit()
        cat_id = cat.id
        entry = parse_entries("@article{k, title={CatPaper}, year={2022}}")[0]
        result = import_single_entry(entry, uid, category_id=cat_id)
        db.session.commit()
        assert result["created"].category_id == cat_id


def test_import_single_entry_does_not_commit(app):
    """Caller must commit/rollback. Verify the helper itself leaves the session
    in an uncommitted state so callers can compose multiple operations."""
    uid = _seed_user(app, "u_nocommit")
    with app.app_context():
        entry = parse_entries("@article{k, title={Trans}, year={2022}}")[0]
        result = import_single_entry(entry, uid)
        assert result["created"] is not None
        db.session.rollback()
        assert Document.query.filter_by(user_id=uid, title="Trans").count() == 0


def test_import_bibtex_backward_compatible(app):
    """The existing /bibtex/import endpoint uses this; behavior must be unchanged."""
    uid = _seed_user(app, "u_compat")
    with app.app_context():
        text = (
            "@article{a, title={A1}, year={2020}}\n"
            "@article{b, title={}, year={2021}}\n"  # skipped - no title
            "@article{c, title={A1}, year={2020}}"  # skipped - duplicate of first
        )
        created, skipped = import_bibtex(text, uid)
        assert created == 1
        assert skipped == 2
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_bibtex_io.py -v`
Expected: 新加的 6 个测试 FAIL with ImportError on `import_single_entry`

- [ ] **Step 3: 修改 `app/services/bibtex_io.py`**

把 `import_bibtex` 函数整体替换为：

```python
def import_single_entry(
    entry: dict, user_id: int, category_id: int | None = None
) -> dict:
    """Persist a single bibtex entry as a Document. Returns
    ``{"created": Document|None, "skipped_reason": str|None}``.

    Does NOT commit; the caller chooses the transaction boundary so multiple
    operations (e.g. attaching a PDF) can roll back atomically.

    Reasons a row may be skipped:
    - Empty/missing title
    - DOI matches an existing Document for this user
    - (title, publication_year) matches an existing Document for this user
    """
    title = entry.get("title", "").strip().strip("{}")
    if not title:
        return {"created": None, "skipped_reason": "缺少 title 字段"}

    doi = entry.get("doi", "").strip() or None
    year_raw = entry.get("year", "").strip()
    try:
        year = int(year_raw) if year_raw else None
    except ValueError:
        year = None

    existing = None
    if doi:
        existing = Document.query.filter_by(user_id=user_id, doi=doi).first()
    if not existing:
        existing = Document.query.filter_by(
            user_id=user_id, title=title, publication_year=year
        ).first()
    if existing:
        return {
            "created": None,
            "skipped_reason": f"已存在文献 ID {existing.id}: {existing.title}",
        }

    bib_type = entry.get("ENTRYTYPE", "misc").lower()
    doc_type = _BIB_TYPE_TO_DOCTYPE.get(bib_type, "other")

    journal = entry.get("journal") or entry.get("booktitle")
    publisher = entry.get("publisher")
    source_type = "journal" if bib_type == "article" else (
        "conference" if bib_type in ("inproceedings", "conference") else "other"
    )
    source = (
        upsert.get_or_create_source(journal, user_id, source_type, publisher)
        if journal else None
    )

    doc = Document(
        user_id=user_id,
        title=title,
        abstract=entry.get("abstract"),
        document_type=doc_type,
        publication_year=year,
        volume=entry.get("volume"),
        issue=entry.get("number") or entry.get("issue"),
        pages=entry.get("pages"),
        doi=doi,
        source=source,
        category_id=category_id,
    )
    db.session.add(doc)
    db.session.flush()

    authors_raw = entry.get("author", "")
    author_names = [a.strip() for a in authors_raw.split(" and ") if a.strip()]
    for i, name in enumerate(author_names, start=1):
        author = upsert.get_or_create_author_lenient(name, user_id)
        db.session.add(
            DocumentAuthor(document_id=doc.id, author_id=author.id, author_order=i)
        )

    kw_raw = entry.get("keywords", "")
    for kw_name in upsert.parse_csv_list(kw_raw):
        doc.keywords.append(upsert.get_or_create_keyword(kw_name, user_id))

    return {"created": doc, "skipped_reason": None}


def import_bibtex(bib_text: str, user_id: int) -> Tuple[int, int]:
    """Parse a .bib string and create Documents. Returns (created, skipped)."""
    created = 0
    skipped = 0
    for entry in parse_entries(bib_text):
        result = import_single_entry(entry, user_id)
        if result["created"]:
            created += 1
        else:
            skipped += 1
    db.session.commit()
    return created, skipped
```

注意 imports：保留文件顶部既有 `from . import upsert`。`Tuple` import 已存在。`Optional` 类型可以用 `int | None` 因为项目用 Python 3.10+（看 `documents.py` 已用此语法）。

- [ ] **Step 4: 跑全部测试**

Run: `python -m pytest tests -v`
Expected: 全部 PASS（含 `test_import_bibtex_backward_compatible` 验证旧入口未回归）。

- [ ] **Step 5: 提交**

```bash
git add app/services/bibtex_io.py tests/test_bibtex_io.py
git commit -m "refactor(bibtex_io): 抽出 import_single_entry, 支持 category_id, 旧 API 包装"
```

---

## Task 5: `batch_bibtex` Blueprint 骨架 + GET 页面 + 注册

**Files:**
- Create: `app/blueprints/batch_bibtex.py`
- Create: `app/templates/bibtex/batch.html`（先放骨架，Task 9 才填完整 UI）
- Modify: `app/__init__.py:37-50`
- Test: `tests/test_batch_bibtex.py`

GET 页面只需渲染模板，把 `categories` 与 `mineru_url` 透给前端。

- [ ] **Step 1: 写失败测试 `tests/test_batch_bibtex.py`**

```python
def test_batch_page_requires_login(client):
    resp = client.get("/bibtex/batch", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_batch_page_renders(login_client):
    resp = login_client.get("/bibtex/batch")
    assert resp.status_code == 200
    assert "批量识别 PDF".encode("utf-8") in resp.data
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_batch_bibtex.py -v`
Expected: FAIL with 404（路由未注册）

- [ ] **Step 3: 创建 `app/blueprints/batch_bibtex.py`**

```python
"""批量 PDF 识别 + 批量 BibTeX 入库蓝图。

三个端点都是单篇粒度的；批次概念完全由前端 JS 编排。
"""

from flask import Blueprint, render_template
from flask_login import login_required, current_user

from ..extensions import db
from ..models import Category, UserSetting

bp = Blueprint("batch_bibtex", __name__)


@bp.route("/batch", methods=["GET"])
@login_required
def batch_page():
    uid = current_user.id
    categories = Category.query.filter_by(user_id=uid).order_by(Category.name).all()
    s = db.session.get(UserSetting, uid)
    mineru_url = (s.mineru_url if s and s.mineru_url else "").strip() or "http://127.0.0.1:8000"
    return render_template(
        "bibtex/batch.html",
        categories=categories,
        mineru_url=mineru_url,
    )
```

- [ ] **Step 4: 创建 `app/templates/bibtex/batch.html` 骨架**

```html
{% extends "base.html" %}
{% block title %}批量识别 PDF{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4 class="mb-0">批量识别 PDF · 批量入库</h4>
  <a class="btn btn-link" href="{{ url_for('documents.list_documents') }}">返回文献库</a>
</div>

<div id="batch-app"
     data-mineru-url="{{ mineru_url }}"
     data-categories='{{ categories | tojson | safe }}'>
  <p class="text-muted">（占位：Task 9 之后此区域会被前端 JS 替换为完整 UI）</p>
</div>
{% endblock %}
```

注意 `categories` 在 Jinja 里 `tojson` 出来是 SQLAlchemy 对象，不会直接可序列化——需要在 Python 端先转为 dict 列表。修改 `batch_page` 函数：

```python
    categories_payload = [
        {"id": c.id, "name": c.name} for c in categories
    ]
    return render_template(
        "bibtex/batch.html",
        categories=categories_payload,
        mineru_url=mineru_url,
    )
```

- [ ] **Step 5: 注册 Blueprint。修改 `app/__init__.py:37-50`**

在 imports 区追加：

```python
    from .blueprints.batch_bibtex import bp as batch_bibtex_bp
```

在 register 区追加（紧跟 `bibtex_bp` 之后，共用 `/bibtex` 前缀）：

```python
    app.register_blueprint(batch_bibtex_bp, url_prefix="/bibtex")
```

完整修改后的"导入各个蓝图"+"注册蓝图"段：

```python
    # 导入各个蓝图
    from .blueprints.auth import bp as auth_bp
    from .blueprints.documents import bp as documents_bp
    from .blueprints.categories import bp as categories_bp
    from .blueprints.library import bp as library_bp
    from .blueprints.bibtex import bp as bibtex_bp
    from .blueprints.batch_bibtex import bp as batch_bibtex_bp
    from .blueprints.settings import bp as settings_bp

    # 注册蓝图，并设置 URL 前缀
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(documents_bp, url_prefix="/documents")
    app.register_blueprint(categories_bp, url_prefix="/categories")
    app.register_blueprint(library_bp, url_prefix="/library")
    app.register_blueprint(bibtex_bp, url_prefix="/bibtex")
    app.register_blueprint(batch_bibtex_bp, url_prefix="/bibtex")
    app.register_blueprint(settings_bp, url_prefix="/settings")
```

- [ ] **Step 6: 跑测试确认通过**

Run: `python -m pytest tests/test_batch_bibtex.py -v`
Expected: 2 PASS

- [ ] **Step 7: 提交**

```bash
git add app/blueprints/batch_bibtex.py app/templates/bibtex/batch.html app/__init__.py tests/test_batch_bibtex.py
git commit -m "feat(batch_bibtex): GET /bibtex/batch 页面骨架与 Blueprint 注册"
```

---

## Task 6: POST `/bibtex/batch/recognize`

**Files:**
- Modify: `app/blueprints/batch_bibtex.py`
- Modify: `tests/test_batch_bibtex.py`

单 PDF 上传 → 调 `mineru_client.parse_pdf` → 只回原始 markdown 文本。不抽取 suggested_fields。

- [ ] **Step 1: 在 `tests/test_batch_bibtex.py` 追加失败测试**

```python
def test_batch_recognize_rejects_missing_pdf(login_client):
    resp = login_client.post("/bibtex/batch/recognize", data={})
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["ok"] is False


def test_batch_recognize_rejects_non_pdf(login_client):
    resp = login_client.post(
        "/bibtex/batch/recognize",
        data={"pdf": (io.BytesIO(b"not pdf"), "evil.exe")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400


def test_batch_recognize_rejects_empty_pdf(login_client):
    resp = login_client.post(
        "/bibtex/batch/recognize",
        data={"pdf": (io.BytesIO(b""), "blank.pdf")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400


def test_batch_recognize_success(login_client, upload_pdf, mock_mineru):
    resp = login_client.post(
        "/bibtex/batch/recognize",
        data={"pdf": upload_pdf("paper.pdf")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    assert payload["filename"] == "paper.pdf"
    assert "Fake markdown body." in payload["markdown"]
    # 关键：不应返回 suggested_fields（与单篇 recognize_pdf 不同）
    assert "suggested_fields" not in payload
    assert len(mock_mineru) == 1


def test_batch_recognize_mineru_error_returns_502(login_client, upload_pdf, monkeypatch):
    from app.services import mineru_client
    def boom(*a, **kw):
        raise mineru_client.MineruError("MinerU 挂了")
    monkeypatch.setattr(mineru_client, "parse_pdf", boom)
    resp = login_client.post(
        "/bibtex/batch/recognize",
        data={"pdf": upload_pdf("p.pdf")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 502
    payload = resp.get_json()
    assert payload["ok"] is False
    assert "MinerU" in payload["error"]
```

在文件顶部加 `import io`。

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_batch_bibtex.py::test_batch_recognize_success -v`
Expected: FAIL with 404

- [ ] **Step 3: 在 `app/blueprints/batch_bibtex.py` 追加端点**

在文件顶部 imports 追加：

```python
from flask import jsonify, request

from ..services import mineru_client
```

在文件末尾追加：

```python
@bp.route("/batch/recognize", methods=["POST"])
@login_required
def recognize():
    f = request.files.get("pdf")
    if not f or not f.filename:
        return jsonify(ok=False, error="未上传 PDF"), 400
    if not f.filename.lower().endswith(".pdf"):
        return jsonify(ok=False, error="仅支持 PDF 文件"), 400

    file_bytes = f.read()
    if not file_bytes:
        return jsonify(ok=False, error="PDF 文件为空"), 400

    uid = current_user.id
    s = db.session.get(UserSetting, uid)
    base_url = (s.mineru_url if s and s.mineru_url else "").strip() or "http://127.0.0.1:8000"

    try:
        parsed = mineru_client.parse_pdf(
            base_url, file_bytes, f.filename, backend="pipeline"
        )
    except mineru_client.MineruError as e:
        return jsonify(ok=False, error=str(e)), 502

    return jsonify(
        ok=True,
        filename=f.filename,
        markdown=parsed.get("md", ""),
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_batch_bibtex.py -v`
Expected: 全部 PASS（5 个 recognize 用例 + 2 个 page 用例）

- [ ] **Step 5: 提交**

```bash
git add app/blueprints/batch_bibtex.py tests/test_batch_bibtex.py
git commit -m "feat(batch_bibtex): POST /bibtex/batch/recognize 单篇识别端点"
```

---

## Task 7: POST `/bibtex/batch/import`（含孤儿附件清理）

**Files:**
- Modify: `app/blueprints/batch_bibtex.py`
- Modify: `tests/test_batch_bibtex.py`

最复杂的端点：接 PDF + bib_text + 可选 category_id → 解析 .bib（必须恰好 1 条）→ 调 `import_single_entry` → 调 `save_uploaded_files` → commit；任何一步失败回滚并清理已写入的 PDF。

- [ ] **Step 1: 在 `tests/test_batch_bibtex.py` 追加失败测试**

```python
def test_batch_import_creates_document_with_attachment(login_client, upload_pdf, seeded_user_id):
    bib = "@article{k, title={Batched Paper}, year={2023}, author={Alice}, doi={10.7/x}}"
    resp = login_client.post(
        "/bibtex/batch/import",
        data={
            "pdf": upload_pdf("batched.pdf"),
            "bib_text": bib,
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    assert payload["title"] == "Batched Paper"

    from app.models import Document, File
    doc = Document.query.filter_by(user_id=seeded_user_id, title="Batched Paper").first()
    assert doc is not None
    assert doc.publication_year == 2023
    assert len(doc.files) == 1
    assert doc.files[0].original_name == "batched.pdf"


def test_batch_import_bib_empty(login_client, upload_pdf):
    resp = login_client.post(
        "/bibtex/batch/import",
        data={"pdf": upload_pdf(), "bib_text": ""},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is False
    assert payload["reason"] == "bib_empty"


def test_batch_import_bib_multi_entry(login_client, upload_pdf):
    bib = (
        "@article{a, title={A}, year={2020}}\n"
        "@article{b, title={B}, year={2021}}"
    )
    resp = login_client.post(
        "/bibtex/batch/import",
        data={"pdf": upload_pdf(), "bib_text": bib},
        content_type="multipart/form-data",
    )
    payload = resp.get_json()
    assert payload["ok"] is False
    assert payload["reason"] == "bib_multi_entry"


def test_batch_import_bib_parse_failed(login_client, upload_pdf):
    # 让 parse_entries 抛异常
    from unittest.mock import patch
    with patch("app.blueprints.batch_bibtex.bibtex_io.parse_entries",
               side_effect=ValueError("malformed")):
        resp = login_client.post(
            "/bibtex/batch/import",
            data={"pdf": upload_pdf(), "bib_text": "@@bogus"},
            content_type="multipart/form-data",
        )
    payload = resp.get_json()
    assert payload["ok"] is False
    assert payload["reason"] == "bib_parse_failed"
    assert "malformed" in payload["error_detail"]


def test_batch_import_duplicate_by_doi(login_client, upload_pdf, seeded_user_id, app):
    from app.extensions import db
    from app.models import Document, File
    with app.app_context():
        existing = Document(user_id=seeded_user_id, title="Old", doi="10.99/dup")
        db.session.add(existing)
        db.session.commit()
        existing_id = existing.id

    bib = "@article{k, title={Different}, year={2023}, doi={10.99/dup}}"
    resp = login_client.post(
        "/bibtex/batch/import",
        data={"pdf": upload_pdf("dup.pdf"), "bib_text": bib},
        content_type="multipart/form-data",
    )
    payload = resp.get_json()
    assert payload["ok"] is False
    assert payload["reason"] == "duplicate"
    assert str(existing_id) in payload["error_detail"]

    # 关键：被判 duplicate 时不应给已有文献附 PDF
    with app.app_context():
        assert File.query.filter_by(document_id=existing_id).count() == 0


def test_batch_import_rejects_non_pdf_attachment(login_client):
    resp = login_client.post(
        "/bibtex/batch/import",
        data={
            "pdf": (io.BytesIO(b"oops"), "evil.exe"),
            "bib_text": "@article{k, title={T}, year={2020}}",
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400


def test_batch_import_with_category_id(login_client, upload_pdf, seeded_user_id, app):
    from app.extensions import db
    from app.models import Category, Document
    with app.app_context():
        c = Category(user_id=seeded_user_id, name="ML-batch")
        db.session.add(c)
        db.session.commit()
        cat_id = c.id

    bib = "@article{k, title={CatBatch}, year={2024}}"
    resp = login_client.post(
        "/bibtex/batch/import",
        data={
            "pdf": upload_pdf("cb.pdf"),
            "bib_text": bib,
            "category_id": str(cat_id),
        },
        content_type="multipart/form-data",
    )
    payload = resp.get_json()
    assert payload["ok"] is True

    with app.app_context():
        doc = Document.query.filter_by(user_id=seeded_user_id, title="CatBatch").first()
        assert doc.category_id == cat_id


def test_batch_import_rollback_cleans_orphan_attachment(login_client, upload_pdf, app, monkeypatch):
    """If db.session.commit raises after the PDF is written to disk, the orphan
    file must be unlinked."""
    from app.extensions import db
    from app.models import Document
    from sqlalchemy.exc import OperationalError

    calls = {"commit_count": 0}
    real_commit = db.session.commit

    def fake_commit():
        calls["commit_count"] += 1
        # First commit is from import_single_entry — let it through; the next
        # one (after save_uploaded_files) is what we want to fail.
        if calls["commit_count"] == 1:
            raise OperationalError("", {}, Exception("disk full simulation"))
        return real_commit()

    monkeypatch.setattr(db.session, "commit", fake_commit)

    bib = "@article{k, title={Doomed}, year={2024}}"
    resp = login_client.post(
        "/bibtex/batch/import",
        data={"pdf": upload_pdf("doomed.pdf"), "bib_text": bib},
        content_type="multipart/form-data",
    )
    payload = resp.get_json()
    assert payload["ok"] is False
    assert payload["reason"] == "save_failed"

    # No Document created
    with app.app_context():
        assert Document.query.filter_by(title="Doomed").count() == 0

    # No orphan PDF file under uploads/<uid>/
    from flask import current_app
    with app.app_context():
        upload_root = Path(current_app.config["UPLOAD_FOLDER"])
        user_dir = upload_root / "1"  # seeded_user_id is 1 in test DB
        if user_dir.exists():
            assert list(user_dir.iterdir()) == []
```

文件顶部追加 `from pathlib import Path`。

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_batch_bibtex.py -v`
Expected: 8 个新加用例 FAIL with 404

- [ ] **Step 3: 在 `app/blueprints/batch_bibtex.py` 追加端点**

文件顶部 imports 追加：

```python
from ..services import bibtex_io
from ..services.file_io import save_uploaded_files
```

文件末尾追加：

```python
_ALLOWED_ATTACHMENT_EXTS = {"pdf"}  # 批量入口只接受 PDF


def _is_pdf(filename: str) -> bool:
    if not filename or "." not in filename:
        return False
    return filename.rsplit(".", 1)[-1].lower() in _ALLOWED_ATTACHMENT_EXTS


@bp.route("/batch/import", methods=["POST"])
@login_required
def import_one():
    f = request.files.get("pdf")
    bib_text = (request.form.get("bib_text") or "").strip()
    category_id = request.form.get("category_id", type=int)

    if not f or not f.filename:
        return jsonify(ok=False, error="未上传 PDF"), 400
    if not _is_pdf(f.filename):
        return jsonify(ok=False, error="附件必须是 PDF"), 400

    if not bib_text:
        return jsonify(ok=False, reason="bib_empty")

    try:
        entries = bibtex_io.parse_entries(bib_text)
    except Exception as e:
        return jsonify(ok=False, reason="bib_parse_failed", error_detail=str(e))

    if len(entries) != 1:
        return jsonify(
            ok=False,
            reason="bib_multi_entry",
            error_detail=f"该输入框应只含 1 个条目，实际 {len(entries)} 个",
        )

    uid = current_user.id
    try:
        result = bibtex_io.import_single_entry(entries[0], uid, category_id)
    except Exception as e:
        db.session.rollback()
        return jsonify(ok=False, reason="save_failed", error_detail=str(e))

    if result["skipped_reason"]:
        # No Document created → don't write the PDF anywhere
        db.session.rollback()
        return jsonify(ok=False, reason="duplicate", error_detail=result["skipped_reason"])

    doc = result["created"]
    saved_paths: list = []
    try:
        saved_paths, _ = save_uploaded_files(doc, [f], uid)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        for p in saved_paths:
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass
        return jsonify(ok=False, reason="save_failed", error_detail=str(e))

    return jsonify(ok=True, document_id=doc.id, title=doc.title)
```

注意：`import_single_entry` 在"缺标题"或"重复"时返回 skipped_reason，并不需要 rollback——因为它在这条路径上没 add 任何东西到 session。但我们调用了 `db.session.add(doc)` 之前的查重会先发生（在 import_single_entry 内部）。安全起见，命中 skip 后**显式 rollback**让 session 干净。已在代码里写明。

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_batch_bibtex.py -v`
Expected: 全部 PASS（含孤儿清理用例）。

如果某个用例 FAIL，按提示修复。**特别留意 `test_batch_import_rollback_cleans_orphan_attachment`**：sqlite in-memory 下文件确实会被写到磁盘 `uploads/1/`；这是测试需要的真实行为。

- [ ] **Step 5: 提交**

```bash
git add app/blueprints/batch_bibtex.py tests/test_batch_bibtex.py
git commit -m "feat(batch_bibtex): POST /bibtex/batch/import 单条入库, 含孤儿附件清理"
```

---

## Task 8: 文献列表页加「批量识别 PDF」入口按钮

**Files:**
- Modify: `app/templates/documents/list.html:29-34`

- [ ] **Step 1: 修改 `app/templates/documents/list.html`**

替换第 28-34 行的按钮区：

```html
      <div>
        <a class="btn btn-primary" href="{{ url_for('documents.new') }}">
          <i class="bi bi-plus-lg"></i> 新增文献
        </a>
        <a class="btn btn-outline-secondary" href="{{ url_for('bibtex.import_form') }}">导入 BibTeX</a>
        <a class="btn btn-outline-secondary" href="{{ url_for('batch_bibtex.batch_page') }}">批量识别 PDF</a>
      </div>
```

- [ ] **Step 2: 起服务手工验证**

Run: `python run.py`（在另一个终端起 MinerU 或先不起也行）
浏览器打开 `http://127.0.0.1:5000/documents`，登录后应看到三个按钮，点「批量识别 PDF」跳转到 `/bibtex/batch`，页面显示占位内容。

- [ ] **Step 3: 提交**

```bash
git add app/templates/documents/list.html
git commit -m "feat(ui): 文献列表页加批量识别 PDF 入口按钮"
```

---

## Task 9: `batch.html` 完整模板 + marked.js 静态资源

**Files:**
- Create: `app/static/vendor/marked.min.js`（下载本地副本，避免依赖外网 CDN）
- Modify: `app/templates/bibtex/batch.html`

把骨架替换为完整的两态 UI：状态 0（拖拽/选文件 + 默认分类下拉 + 提示）、状态 1（左侧文件列表 + 右侧分屏）。

- [ ] **Step 1: 下载 marked.js 到本地**

```bash
mkdir -p "D:/GitHub项目/Personal_Library/app/static/vendor"
curl -L -o "D:/GitHub项目/Personal_Library/app/static/vendor/marked.min.js" "https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"
```

如果 curl 不可用，用 PowerShell：

```powershell
Invoke-WebRequest -Uri "https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js" -OutFile "D:\GitHub项目\Personal_Library\app\static\vendor\marked.min.js"
```

验证文件存在且 >20KB：

```bash
ls -la "D:/GitHub项目/Personal_Library/app/static/vendor/marked.min.js"
```

- [ ] **Step 2: 整体替换 `app/templates/bibtex/batch.html`**

```html
{% extends "base.html" %}
{% block title %}批量识别 PDF{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4 class="mb-0">批量识别 PDF · 批量入库</h4>
  <a class="btn btn-link" href="{{ url_for('documents.list_documents') }}">返回文献库</a>
</div>

<div id="mineru-banner" class="alert alert-warning d-none" role="alert">
  <span id="mineru-banner-msg"></span>
  <a href="{{ url_for('settings.index') }}" class="alert-link">去设置 MinerU URL</a>
</div>

<div id="batch-app"
     data-mineru-url="{{ mineru_url }}"
     data-categories='{{ categories | tojson | safe }}'
     data-recognize-url="{{ url_for('batch_bibtex.recognize') }}"
     data-import-url="{{ url_for('batch_bibtex.import_one') }}">

  <!-- 状态 0: 空状态 -->
  <section id="state-empty" class="card">
    <div class="card-body text-center py-5">
      <p class="mb-3">拖入或点击选择多个 PDF（上限 20 篇）</p>
      <input type="file" id="pdf-input" accept="application/pdf,.pdf" multiple class="d-none">
      <button type="button" id="pick-files-btn" class="btn btn-primary">选择文件</button>
      <div class="mt-3 d-inline-block text-start">
        <label class="form-label small mb-1">默认分类（可选；应用到本批所有篇目）</label>
        <select id="default-category" class="form-select form-select-sm" style="min-width: 220px">
          <option value="">— 不分类 —</option>
          {% for c in categories %}<option value="{{ c.id }}">{{ c.name }}</option>{% endfor %}
        </select>
      </div>
      <p class="text-muted small mt-3 mb-0">提示：识别期间不要关闭浏览器；.bib 草稿会自动保存到本地</p>
    </div>
  </section>

  <!-- 状态 1: 识别 + 填写 -->
  <section id="state-working" class="d-none">
    <div class="row g-3">
      <aside class="col-md-3">
        <div class="card">
          <div class="card-header d-flex justify-content-between align-items-center">
            <span>文件 (<span id="file-count">0</span>)</span>
          </div>
          <ul id="file-list" class="list-group list-group-flush"></ul>
          <div class="card-body d-grid gap-2">
            <button type="button" id="retry-failed-btn" class="btn btn-outline-secondary btn-sm" disabled>重识别失败项</button>
            <button type="button" id="submit-all-btn" class="btn btn-success btn-sm" disabled>批量提交</button>
            <a href="{{ url_for('batch_bibtex.batch_page') }}" class="btn btn-link btn-sm">清空重来</a>
          </div>
        </div>
      </aside>
      <main class="col-md-9">
        <div id="empty-pane" class="alert alert-light text-center py-5">请在左侧点击一篇开始填写 .bib</div>
        <div id="split-pane" class="d-none">
          <div class="row g-2">
            <div class="col-md-6">
              <div class="card h-100">
                <div class="card-header d-flex justify-content-between align-items-center">
                  <span id="md-filename" class="small text-muted"></span>
                  <span id="md-status" class="badge bg-secondary">—</span>
                </div>
                <div class="card-body" style="max-height: 70vh; overflow-y: auto;">
                  <div id="md-render"></div>
                </div>
              </div>
            </div>
            <div class="col-md-6">
              <div class="card h-100">
                <div class="card-header">.bib 输入</div>
                <div class="card-body">
                  <textarea id="bib-input" class="form-control font-monospace" rows="20"
                            placeholder="@article{key,&#10;  title  = {},&#10;  author = {},&#10;  year   = {},&#10;}"></textarea>
                  <div id="bib-feedback" class="small text-muted mt-2">—</div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div id="result-summary" class="alert alert-info mt-3 d-none"></div>
      </main>
    </div>
  </section>
</div>

<script src="{{ url_for('static', filename='vendor/marked.min.js') }}"></script>
<script src="{{ url_for('static', filename='js/batch_bibtex.js') }}"></script>
{% endblock %}
```

- [ ] **Step 3: 跑测试确认页面渲染未坏**

Run: `python -m pytest tests/test_batch_bibtex.py::test_batch_page_renders -v`
Expected: PASS

- [ ] **Step 4: 起服务手工验证**

Run: `python run.py`
浏览器 `/bibtex/batch`：应看到状态 0 UI（选择文件按钮、默认分类下拉、提示语），开发者工具 Network 标签确认 `marked.min.js` 200 加载。

- [ ] **Step 5: 提交**

```bash
git add app/static/vendor/marked.min.js app/templates/bibtex/batch.html
git commit -m "feat(batch_bibtex): 批量页完整 UI 骨架 + 本地 marked.js"
```

---

## Task 10: 前端 JS 识别阶段状态机

**Files:**
- Create: `app/static/js/batch_bibtex.js`

实现"选文件 → 串行调识别接口 → 左侧列表实时显示状态 → 点击篇目右侧分屏出 markdown"这一段。

- [ ] **Step 1: 创建 `app/static/js/batch_bibtex.js`**

```javascript
/* 批量 PDF 识别 + 批量入库 前端状态机
 *
 * 单页 SPA-like：
 *   状态 0 (#state-empty)：未选文件
 *   状态 1 (#state-working)：识别中 / 填写中 / 提交中 / 完成
 *
 * 每个文件项 (Item) 形如：
 *   {
 *     id: <hash>,              // 由 filename+size+lastModified 派生
 *     file: File,              // 浏览器 File 对象，PDF blob
 *     filename: string,
 *     status: "queued" | "recognizing" | "recognized" | "rec_failed"
 *           | "submitting"  | "imported"     | "import_failed" | "skipped",
 *     markdown: string | null,
 *     bibText: string,         // localStorage 持久化
 *     errorMsg: string | null,
 *     documentId: number | null,
 *   }
 */
(function () {
  'use strict';

  const MAX_FILES = 20;
  const LS_PREFIX = 'batchbib:v1:';
  const LS_TTL_MS = 7 * 24 * 60 * 60 * 1000;  // 7 天
  const DRAFT_DEBOUNCE_MS = 500;

  const root = document.getElementById('batch-app');
  if (!root) return;
  const RECOGNIZE_URL = root.dataset.recognizeUrl;
  const IMPORT_URL = root.dataset.importUrl;
  const MINERU_URL = root.dataset.mineruUrl;

  const els = {
    empty: document.getElementById('state-empty'),
    working: document.getElementById('state-working'),
    input: document.getElementById('pdf-input'),
    pickBtn: document.getElementById('pick-files-btn'),
    list: document.getElementById('file-list'),
    count: document.getElementById('file-count'),
    retryBtn: document.getElementById('retry-failed-btn'),
    submitBtn: document.getElementById('submit-all-btn'),
    emptyPane: document.getElementById('empty-pane'),
    splitPane: document.getElementById('split-pane'),
    mdFilename: document.getElementById('md-filename'),
    mdStatus: document.getElementById('md-status'),
    mdRender: document.getElementById('md-render'),
    bibInput: document.getElementById('bib-input'),
    bibFeedback: document.getElementById('bib-feedback'),
    summary: document.getElementById('result-summary'),
    defaultCategory: document.getElementById('default-category'),
  };

  /** Items array, ordered as selected. */
  const items = [];
  /** Index of currently displayed item, or null. */
  let activeIdx = null;
  /** True while a recognize/import request is in flight (we serialize). */
  let queueBusy = false;

  // -------- Hash & localStorage --------

  function hashId(file) {
    return `${file.name}|${file.size}|${file.lastModified}`;
  }

  function lsKey(id) { return LS_PREFIX + id; }

  function loadDraft(id) {
    try {
      const raw = localStorage.getItem(lsKey(id));
      if (!raw) return '';
      const obj = JSON.parse(raw);
      if (Date.now() - obj.ts > LS_TTL_MS) {
        localStorage.removeItem(lsKey(id));
        return '';
      }
      return obj.text || '';
    } catch (e) { return ''; }
  }

  function saveDraft(id, text) {
    try {
      localStorage.setItem(lsKey(id), JSON.stringify({ ts: Date.now(), text }));
    } catch (e) {
      console.warn('localStorage 草稿保存失败', e);
    }
  }

  function clearDraft(id) {
    try { localStorage.removeItem(lsKey(id)); } catch (e) { }
  }

  function purgeOldDrafts() {
    try {
      for (let i = localStorage.length - 1; i >= 0; i--) {
        const k = localStorage.key(i);
        if (!k || !k.startsWith(LS_PREFIX)) continue;
        try {
          const obj = JSON.parse(localStorage.getItem(k));
          if (Date.now() - obj.ts > LS_TTL_MS) localStorage.removeItem(k);
        } catch (e) {
          localStorage.removeItem(k);
        }
      }
    } catch (e) { }
  }

  // -------- File picker --------

  els.pickBtn.addEventListener('click', () => els.input.click());
  els.input.addEventListener('change', (e) => onFilesPicked(e.target.files));

  function onFilesPicked(fileList) {
    const files = Array.from(fileList).filter(f => f.name.toLowerCase().endsWith('.pdf'));
    if (files.length === 0) {
      alert('请选择 PDF 文件');
      return;
    }
    if (files.length > MAX_FILES) {
      alert(`单次最多 ${MAX_FILES} 篇，本次选了 ${files.length} 篇`);
      return;
    }
    purgeOldDrafts();

    for (const file of files) {
      const id = hashId(file);
      if (items.some(it => it.id === id)) continue;
      items.push({
        id,
        file,
        filename: file.name,
        status: 'queued',
        markdown: null,
        bibText: loadDraft(id),
        errorMsg: null,
        documentId: null,
      });
    }
    els.empty.classList.add('d-none');
    els.working.classList.remove('d-none');
    renderList();
    pumpRecognizeQueue();
  }

  // -------- List rendering --------

  const STATUS_LABEL = {
    queued: { icon: '⌛', text: '排队中', cls: 'text-muted' },
    recognizing: { icon: '⟳', text: '识别中', cls: 'text-primary' },
    recognized: { icon: '✔', text: '待填写', cls: 'text-success' },
    rec_failed: { icon: '✘', text: '识别失败', cls: 'text-danger' },
    submitting: { icon: '⟳', text: '入库中', cls: 'text-primary' },
    imported: { icon: '✓', text: '已入库', cls: 'text-success' },
    import_failed: { icon: '✘', text: '入库失败', cls: 'text-danger' },
    skipped: { icon: '⊘', text: '跳过', cls: 'text-warning' },
  };

  function renderList() {
    els.count.textContent = String(items.length);
    els.list.innerHTML = '';
    items.forEach((it, idx) => {
      const li = document.createElement('li');
      li.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-center';
      if (idx === activeIdx) li.classList.add('active');
      const status = STATUS_LABEL[it.status] || STATUS_LABEL.queued;
      li.innerHTML = `
        <span class="text-truncate" style="max-width: 70%" title="${escapeHtml(it.filename)}">${escapeHtml(it.filename)}</span>
        <span class="${status.cls}" title="${escapeHtml(it.errorMsg || status.text)}">${status.icon} ${status.text}</span>`;
      li.addEventListener('click', () => selectItem(idx));
      els.list.appendChild(li);
    });
    refreshButtons();
  }

  function refreshButtons() {
    const hasFailed = items.some(it => it.status === 'rec_failed');
    els.retryBtn.disabled = !hasFailed || queueBusy;
    const canSubmit = items.some(it => it.status === 'recognized' && it.bibText.trim().length > 0);
    els.submitBtn.disabled = !canSubmit || queueBusy;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    })[c]);
  }

  // -------- Recognize queue (serial) --------

  async function pumpRecognizeQueue() {
    if (queueBusy) return;
    const next = items.find(it => it.status === 'queued');
    if (!next) { renderList(); return; }
    queueBusy = true;
    next.status = 'recognizing';
    renderList();
    try {
      const form = new FormData();
      form.append('pdf', next.file, next.filename);
      const resp = await fetch(RECOGNIZE_URL, { method: 'POST', body: form });
      const data = await resp.json();
      if (!resp.ok || !data.ok) {
        next.status = 'rec_failed';
        next.errorMsg = data.error || `HTTP ${resp.status}`;
      } else {
        next.status = 'recognized';
        next.markdown = data.markdown || '';
        next.errorMsg = null;
      }
    } catch (e) {
      next.status = 'rec_failed';
      next.errorMsg = String(e);
    } finally {
      queueBusy = false;
      renderList();
      // 若当前选中的就是这一项，刷新右侧
      if (activeIdx !== null && items[activeIdx] === next) selectItem(activeIdx);
      pumpRecognizeQueue();  // 继续下一个
    }
  }

  // -------- Item selection / split pane --------

  function selectItem(idx) {
    activeIdx = idx;
    const it = items[idx];
    if (!it) return;
    renderList();
    els.emptyPane.classList.add('d-none');
    els.splitPane.classList.remove('d-none');
    els.mdFilename.textContent = it.filename;
    const status = STATUS_LABEL[it.status] || STATUS_LABEL.queued;
    els.mdStatus.textContent = `${status.icon} ${status.text}`;
    els.mdStatus.className = `badge bg-${status.cls.replace('text-', '')}`;

    if (it.status === 'recognized' || it.status === 'imported' || it.status === 'import_failed') {
      renderMarkdown(it.markdown || '');
    } else if (it.status === 'rec_failed') {
      els.mdRender.innerHTML = `<div class="alert alert-danger">${escapeHtml(it.errorMsg || '识别失败')}</div>`;
    } else {
      els.mdRender.innerHTML = '<div class="text-muted">识别中…请稍候</div>';
    }
    els.bibInput.value = it.bibText || '';
    updateBibFeedback(it.bibText || '');
  }

  function renderMarkdown(md) {
    if (md.length > 200 * 1024) {
      els.mdRender.innerHTML = `<div class="alert alert-warning">原文过长（${(md.length/1024).toFixed(0)}KB），仅显示前 50KB</div><pre style="white-space: pre-wrap">${escapeHtml(md.slice(0, 50 * 1024))}</pre>`;
      return;
    }
    try {
      els.mdRender.innerHTML = window.marked.parse(md);
    } catch (e) {
      els.mdRender.innerHTML = `<pre style="white-space: pre-wrap">${escapeHtml(md)}</pre>`;
    }
  }

  function updateBibFeedback(text) {
    const trimmed = text.trim();
    if (!trimmed) {
      els.bibFeedback.textContent = '（未填写；提交时将跳过此篇）';
      els.bibFeedback.className = 'small text-muted mt-2';
      return;
    }
    const matches = trimmed.match(/^@\w+\s*\{/gm) || [];
    if (matches.length === 0) {
      els.bibFeedback.textContent = '格式可疑：未发现 @type{ 开头';
      els.bibFeedback.className = 'small text-danger mt-2';
    } else if (matches.length === 1) {
      els.bibFeedback.textContent = `已识别为 1 个条目（${matches[0].slice(0, -1)}）`;
      els.bibFeedback.className = 'small text-success mt-2';
    } else {
      els.bibFeedback.textContent = `检测到 ${matches.length} 个条目：该输入框只能填 1 个，提交时会被拒绝`;
      els.bibFeedback.className = 'small text-danger mt-2';
    }
  }

  // -------- Bib textarea autosave (defined here, used by Task 11 too) --------

  let draftTimer = null;
  els.bibInput.addEventListener('input', () => {
    if (activeIdx === null) return;
    const it = items[activeIdx];
    it.bibText = els.bibInput.value;
    updateBibFeedback(it.bibText);
    clearTimeout(draftTimer);
    draftTimer = setTimeout(() => saveDraft(it.id, it.bibText), DRAFT_DEBOUNCE_MS);
    refreshButtons();
  });

  // -------- Retry --------

  els.retryBtn.addEventListener('click', () => {
    items.forEach(it => {
      if (it.status === 'rec_failed') {
        it.status = 'queued';
        it.errorMsg = null;
      }
    });
    renderList();
    pumpRecognizeQueue();
  });

  // -------- Init --------

  purgeOldDrafts();

  // 暴露给 Task 12 提交逻辑使用
  window.__batchApp = { items, els, selectItem, renderList, refreshButtons, clearDraft, MAX_FILES };
})();
```

- [ ] **Step 2: 起服务手工验证识别阶段**

Run: `python run.py`（确保 MinerU 也在跑 `mineru-api` 默认端口）
浏览器 `/bibtex/batch`：
- 点「选择文件」选 2-3 个 PDF
- 左侧应出现列表，每项从 "⌛排队中" → "⟳识别中" → "✔待填写"（或 "✘识别失败"）
- 点已识别项，右侧应出现分屏，左半渲染 markdown，右半空 textarea
- 在 textarea 输入文字，等 1 秒看 DevTools 的 localStorage 应出现 `batchbib:v1:*` 键
- 刷新页面 → 回到状态 0，再次选同一 PDF → 右侧 textarea 自动恢复刚填的内容

如果 MinerU 不可用，识别会失败但前端状态机仍应正确切到"✘ 识别失败"并允许「重识别失败项」。

- [ ] **Step 3: 提交**

```bash
git add app/static/js/batch_bibtex.js
git commit -m "feat(batch_bibtex/ui): 前端识别队列状态机 + 草稿持久化"
```

---

## Task 11: 前端 `.bib` 填写完善 + beforeunload 提醒

**Files:**
- Modify: `app/static/js/batch_bibtex.js`

Task 10 已经实现了草稿写 localStorage 与从 localStorage 恢复，现在加 `beforeunload` 提示和草稿恢复时的轻提示。

- [ ] **Step 1: 在 `app/static/js/batch_bibtex.js` 末尾追加（在 `window.__batchApp = {...}` 之前）**

```javascript
  // -------- beforeunload 提醒 --------

  window.addEventListener('beforeunload', (e) => {
    // 仅当有未入库且 .bib 非空的项时才提醒
    const dirty = items.some(it =>
      (it.status === 'recognized' || it.status === 'rec_failed' || it.status === 'import_failed')
      && it.bibText.trim().length > 0
    );
    if (dirty) {
      e.preventDefault();
      e.returnValue = '未提交的内容已保存在本地草稿，确认离开？';
      return e.returnValue;
    }
  });
```

并在 `onFilesPicked` 加入一行轻提示——如果恢复到至少一篇草稿，flash 一行。修改 `onFilesPicked` 函数末尾：

```javascript
    els.empty.classList.add('d-none');
    els.working.classList.remove('d-none');
    const restored = items.filter(it => it.bibText.length > 0).length;
    if (restored > 0) {
      console.info(`已从本地草稿恢复 ${restored} 篇的 .bib 内容`);
    }
    renderList();
    pumpRecognizeQueue();
```

- [ ] **Step 2: 手工验证**

- 选 PDF、填一些 .bib、不提交 → 关浏览器标签页应弹原生离开确认对话框
- 重新打开同一页面、重新选同一 PDF → 点击该项，右侧 textarea 恢复内容，DevTools console 应看到「已从本地草稿恢复 1 篇」

- [ ] **Step 3: 提交**

```bash
git add app/static/js/batch_bibtex.js
git commit -m "feat(batch_bibtex/ui): beforeunload 防误关 + 草稿恢复轻提示"
```

---

## Task 12: 前端提交队列 + 结果汇总

**Files:**
- Modify: `app/static/js/batch_bibtex.js`

实现「批量提交」按钮：串行调 `/bibtex/batch/import`，更新状态，最后渲染汇总条。

- [ ] **Step 1: 在 `app/static/js/batch_bibtex.js` 末尾追加（同样在 `window.__batchApp` 之前）**

```javascript
  // -------- Submit queue --------

  els.submitBtn.addEventListener('click', async () => {
    await runSubmitQueue();
  });

  async function runSubmitQueue() {
    queueBusy = true;
    refreshButtons();
    const categoryId = els.defaultCategory.value || '';

    let success = 0, skipped = 0, failed = 0;
    const failures = [];

    for (const it of items) {
      // 决定该项命运
      if (it.status === 'imported') { continue; }
      if (it.status === 'rec_failed') {
        it.status = 'skipped';
        it.errorMsg = '识别未完成';
        skipped++; renderList(); continue;
      }
      if (it.status !== 'recognized' && it.status !== 'import_failed') { continue; }
      if (!it.bibText.trim()) {
        it.status = 'skipped';
        it.errorMsg = '未填写 .bib';
        skipped++; renderList(); continue;
      }

      it.status = 'submitting';
      it.errorMsg = null;
      renderList();
      if (activeIdx !== null && items[activeIdx] === it) selectItem(activeIdx);

      try {
        const form = new FormData();
        form.append('pdf', it.file, it.filename);
        form.append('bib_text', it.bibText);
        if (categoryId) form.append('category_id', categoryId);
        const resp = await fetch(IMPORT_URL, { method: 'POST', body: form });
        const data = await resp.json();
        if (resp.ok && data.ok) {
          it.status = 'imported';
          it.documentId = data.document_id;
          it.errorMsg = null;
          clearDraft(it.id);
          success++;
        } else if (resp.ok && data.ok === false && data.reason === 'duplicate') {
          it.status = 'skipped';
          it.errorMsg = data.error_detail || '已存在';
          skipped++;
        } else if (resp.ok && data.ok === false && data.reason === 'bib_empty') {
          it.status = 'skipped';
          it.errorMsg = '未填写 .bib';
          skipped++;
        } else {
          it.status = 'import_failed';
          it.errorMsg = data.error_detail || data.error || data.reason || `HTTP ${resp.status}`;
          failed++;
          failures.push({ filename: it.filename, reason: it.errorMsg });
        }
      } catch (e) {
        it.status = 'import_failed';
        it.errorMsg = String(e);
        failed++;
        failures.push({ filename: it.filename, reason: String(e) });
      }
      renderList();
      if (activeIdx !== null && items[activeIdx] === it) selectItem(activeIdx);
    }

    queueBusy = false;
    renderList();
    showSummary(success, skipped, failed, failures);
  }

  function showSummary(success, skipped, failed, failures) {
    let html = `批量提交完成：<strong class="text-success">${success} 成功</strong>
                · <strong class="text-warning">${skipped} 跳过</strong>
                · <strong class="text-danger">${failed} 失败</strong>`;
    if (success > 0) {
      html += ` · <a href="/documents">查看文献库</a>`;
    }
    if (failures.length > 0) {
      html += '<ul class="mt-2 mb-0">';
      for (const f of failures) {
        html += `<li><code>${escapeHtml(f.filename)}</code>：${escapeHtml(f.reason)}</li>`;
      }
      html += '</ul>';
    }
    els.summary.innerHTML = html;
    els.summary.className = failed > 0 ? 'alert alert-warning mt-3' : 'alert alert-success mt-3';
    els.summary.classList.remove('d-none');
  }
```

- [ ] **Step 2: 手工验证**

启动 MinerU 与 Flask：
1. 选 3 个 PDF，等识别完
2. 给其中 2 个填上合法 .bib（`@article{k, title={X}, year={2024}}`），1 个故意留空
3. 点「批量提交」
4. 期望：
   - 已填的 2 个变 "✓ 已入库"
   - 空的 1 个变 "⊘ 跳过"，错误信息 "未填写 .bib"
   - 底部汇总条 "2 成功 · 1 跳过 · 0 失败"
   - 跳到文献库（点链接）应看到新加的 2 篇文献，每篇有 PDF 附件
5. 把已入库的某篇详情页点开，能下载 PDF 附件
6. 再选同一个 PDF 重试，应得 "⊘ 跳过 - 已存在"

- [ ] **Step 3: 提交**

```bash
git add app/static/js/batch_bibtex.js
git commit -m "feat(batch_bibtex/ui): 批量提交队列 + 结果汇总"
```

---

## Task 13: MinerU 健康预检 + 长 markdown 兜底（已包含）

**Files:**
- Modify: `app/blueprints/batch_bibtex.py`（加 health 端点）
- Modify: `app/static/js/batch_bibtex.js`（页面加载时 ping）

长 markdown 兜底已在 Task 10 `renderMarkdown` 里实现（>200KB 截断）。此任务只补 MinerU 健康预检。

- [ ] **Step 1: 在 `tests/test_batch_bibtex.py` 追加端点测试**

```python
def test_batch_health_passes(login_client, monkeypatch):
    from app.services import mineru_client
    monkeypatch.setattr(mineru_client, "health_check", lambda url, timeout=3.0: {"status": "ok"})
    resp = login_client.get("/bibtex/batch/health")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_batch_health_fails_gracefully(login_client, monkeypatch):
    from app.services import mineru_client
    def boom(url, timeout=3.0):
        raise mineru_client.MineruError("连不上")
    monkeypatch.setattr(mineru_client, "health_check", boom)
    resp = login_client.get("/bibtex/batch/health")
    assert resp.status_code == 200  # 故意 200，让前端按 ok 字段决策
    data = resp.get_json()
    assert data["ok"] is False
    assert "连不上" in data["error"]
```

- [ ] **Step 2: 在 `app/blueprints/batch_bibtex.py` 末尾追加**

```python
@bp.route("/batch/health", methods=["GET"])
@login_required
def batch_health():
    uid = current_user.id
    s = db.session.get(UserSetting, uid)
    base_url = (s.mineru_url if s and s.mineru_url else "").strip() or "http://127.0.0.1:8000"
    try:
        info = mineru_client.health_check(base_url)
    except mineru_client.MineruError as e:
        return jsonify(ok=False, error=str(e), url=base_url)
    return jsonify(ok=True, info=info, url=base_url)
```

- [ ] **Step 3: 跑测试**

Run: `python -m pytest tests/test_batch_bibtex.py -v`
Expected: 全部 PASS

- [ ] **Step 4: 在 `app/static/js/batch_bibtex.js` 文件顶部 IIFE 内、`purgeOldDrafts();` 之后追加**

```javascript
  // -------- MinerU 健康预检 --------

  (async function() {
    try {
      const resp = await fetch('/bibtex/batch/health');
      const data = await resp.json();
      if (!data.ok) {
        const banner = document.getElementById('mineru-banner');
        const msg = document.getElementById('mineru-banner-msg');
        if (banner && msg) {
          msg.textContent = `MinerU 未就绪：${data.error}（${data.url}）`;
          banner.classList.remove('d-none');
        }
        if (els.pickBtn) els.pickBtn.disabled = true;
      }
    } catch (e) {
      console.warn('health check 出错', e);
    }
  })();
```

- [ ] **Step 5: 起服务手工验证**

- 不启 MinerU 直接打开 `/bibtex/batch`：顶部应出现红条「MinerU 未就绪…」，「选择文件」按钮 disabled
- 起 MinerU 再刷新：红条消失，按钮可用

- [ ] **Step 6: 提交**

```bash
git add app/blueprints/batch_bibtex.py app/static/js/batch_bibtex.js tests/test_batch_bibtex.py
git commit -m "feat(batch_bibtex): GET /bibtex/batch/health 预检, 前端不可用时禁用上传"
```

---

## Task 14: 端到端手工验证清单

**Files:**
- 无（验证用）

走通整条用户旅程，对照 spec 「接受标准」9 条逐一打勾。

- [ ] **Step 1: 准备环境**

- 起 MySQL（项目默认连接 `mysql+pymysql://root:@localhost:3306/library_system`）或临时切到 dev 配置
- 起 MinerU：在另一个终端运行 `mineru-api`（默认 `http://127.0.0.1:8000`）
- 起 Flask：`python run.py`

- [ ] **Step 2: 逐条验证 spec 「接受标准」**

| # | 验证步骤 | 期望 |
|---|---|---|
| 1 | 登录 → 打开 `/documents` | 顶部有「批量识别 PDF」按钮，点击跳转 `/bibtex/batch` |
| 2 | 选 3 个 PDF（其中含一个大于 10MB 的） | 左侧列表 3 项；状态依次 ⌛→⟳→✔（或 ✘） |
| 3 | 点已识别项 | 右侧出现分屏：左半 markdown 渲染（标题、段落正常），右半空 textarea |
| 4 | 填一些 .bib，刷新页面，重新选同一 PDF | textarea 恢复刚填的内容 |
| 5 | 全填好，可选下拉一个默认分类，点「批量提交」 | 状态变 ✓ 已入库；底部汇总 "N 成功" |
| 6 | 验证旧 BibTeX 入口未坏：`/bibtex/import` 粘贴一个 .bib 文本 → 导入 | 行为同改动前 |
| 7 | 验证单篇上传未坏：编辑某文献，识别 PDF 仍正常工作 | 编辑页 PDF 识别正常 |
| 8 | 制造失败：在 `_save_uploaded_files` 调用前 inject 一次 `db.session.commit() raise`（或者更简单地填一个一定会被判 duplicate 的 .bib，验证不会留孤儿） | `uploads/<uid>/` 下无孤儿 PDF；Document 表无对应行 |
| 9 | 跑测试套件 | `python -m pytest tests -v` 全 PASS，新加代码覆盖通过观察 |

- [ ] **Step 3: 跑完整测试套件作为最终验证**

Run: `python -m pytest tests -v`
Expected: 全部 PASS（包含原有 + 新增共约 25+ 个用例）

- [ ] **Step 4: （可选）跑覆盖率工具**

如果项目装了 `pytest-cov`：

```bash
python -m pytest tests --cov=app/services/bibtex_io --cov=app/services/file_io --cov=app/blueprints/batch_bibtex -v
```

Expected: 三个目标模块语句覆盖 ≥80%。

- [ ] **Step 5: 写一行短日志到 spec 目录或 CHANGELOG（如项目存在）**

如果 `docs/` 下有 CHANGELOG 或类似文件，追加一行说明本次新增了批量识别+入库功能并指向 spec 与 plan。如无则跳过此步。

- [ ] **Step 6: 最终提交**

如果上面手工验证发现任何小修需要再调，按"发现什么修什么"原则单独 commit。验证全过且无新修改时不需要新 commit；直接到 finishing-a-development-branch 流程合并/PR。

---

## 自审清单（计划完成后过一遍）

**Spec 覆盖：** 9 条接受标准 → Task 14 已逐条对应；3 个端点 → Task 5/6/7；UI 两态 → Task 8/9/10/11/12；错误矩阵 → Task 6/7 测试用例 + Task 13；测试策略 → Task 2/3/4/6/7/13。

**Placeholder 扫描：** 已通读两遍，无 TBD/TODO/"待定"/"类似 Task N"等占位。

**类型一致性：** `save_uploaded_files` 在 Task 2 定义返回 `(saved_paths, skipped_names)`，Task 7 调用方按这个解构 ✓；`import_single_entry` 在 Task 4 定义返回 `{"created", "skipped_reason"}`，Task 7 调用方读 `result["skipped_reason"]` ✓；`parse_entries` 返回 `list[dict]`，Task 7 检查 `len(entries) != 1` ✓。

**风险点：** 
- `test_batch_import_rollback_cleans_orphan_attachment` 假设 sqlite in-memory 下 `seeded_user_id == 1`，这在测试隔离的 fixture 里成立但脆。若失败，把测试改为先查询用户 ID 再拼路径。
- marked.js 走 CDN 下载，若网络不可达需要 Step 1 fallback；已给 PowerShell 备用。
- 前端 JS 没有自动化测试，手工验证清单是唯一防线。
