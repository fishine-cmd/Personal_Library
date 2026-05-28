# 批量 PDF 识别 + 批量 BibTeX 入库 · 设计文档

- 日期：2026-05-29
- 作者：与 Claude 协作
- 影响范围：新增 1 个 Blueprint、1 个模板、1 个前端 JS 文件；重构 `app/services/bibtex_io.py`；从 `app/blueprints/documents.py` 抽出 `_save_uploaded_files` 到公共服务模块

## 背景与目标

当前系统提供两条"识别 / 入库"路径：

1. **单篇 PDF 识别**（`POST /documents/recognize_pdf`）—— 用户在编辑页上传 1 个 PDF，MinerU 解析后用启发式抽取建议字段，用户一键填入或手填，最后保存为 1 篇文献。
2. **BibTeX 文本批量导入**（`POST /bibtex/import`）—— 用户粘贴或上传 1 个 `.bib` 文件，里面可以含多个 entry，全部入库但**没有 PDF 附件**。

两条路径无法配合："批量入库 + 每篇都有 PDF 附件"的需求只能靠用户手动一篇一篇走单篇流程，效率极低。

**目标**：让用户能够一次性提交 N 个 PDF，得到 N 篇带附件的入库文献。具体做法是把"PDF 识别 → 看 markdown 写 .bib → 入库 + 附件"这个流程做成一个**网页内嵌、分屏对照、批量提交**的工作流。

## 非目标

- 不做后台异步任务队列（识别完全由前端串行编排，服务端无状态）
- 不做跨会话的批次持久化（PDF 文件每次都得重新上传；只有 `.bib` 草稿走 localStorage）
- 不做服务端自动从 PDF 抽取 `.bib`（用户必须自己写；启发式抽取仅用于现有单篇流程，本流程不复用）
- 不做并发识别 / 并发入库（前端串行，服务端简化）
- 不引入前端 JS 单元测试框架（与项目现状一致，手工验证为主）

## 用户故事

1. 用户在文献列表点击「批量识别 PDF」→ 进入空状态批量页
2. 用户选择 1–20 个 PDF → 进入双栏页：左侧是文件列表（含状态图标），右侧空白
3. 前端串行调用识别接口，逐篇拿到 markdown；左侧状态从"⟳ 识别中"变为"✔ 已识别"。失败则变成"✘ 失败"，列表项上有错误提示和「重试」按钮
4. 用户点左侧某篇 → 右侧切到分屏：左半渲染 markdown，右半是 `.bib` 输入框（空白模板预填一个 `@article{key,...}` 骨架）
5. 用户对照 markdown 填写 `.bib`，每 500 ms 防抖写入 localStorage
6. 用户全部填完，可选定一个**默认分类**（应用到本批所有篇目），点「批量提交」
7. 前端串行调用入库接口，逐条把 `(PDF, .bib)` 发到服务端；服务端解析 `.bib` → 创建 Document → 保存 PDF 为附件
8. 入库结果在底部条带汇总：N 成功 / M 跳过 / K 失败；失败和跳过项保留草稿可重提
9. 用户点"查看入库的文献"链接 → 跳转 `/documents`

## 架构与模块划分

```
入口（导航）
  └─ 文献列表页 → 新按钮「批量识别 PDF」 → /bibtex/batch
                                          │
                              GET /bibtex/batch              ── 渲染批量页
                              POST /bibtex/batch/recognize   ── 单篇识别（前端串行调用，每次 1 PDF）
                              POST /bibtex/batch/import      ── 单条入库（前端串行调用，每次 1 PDF + 1 entry）

模块复用
  app/services/mineru_client.py   ←   不动
  app/services/pdf_metadata.py    ←   本流程不调用（用户选了空白模板）
  app/services/bibtex_io.py       ←   需重构（详见下文）
  app/blueprints/documents.py
        _save_uploaded_files()    ←   抽到 app/services/file_io.py 共享

新增文件
  app/blueprints/batch_bibtex.py        ← 新 Blueprint（也可并入现有 bibtex.py，但分开更清晰）
  app/templates/bibtex/batch.html       ← 批量页（左列表 + 右分屏）
  app/static/js/batch_bibtex.js         ← 前端状态机
  tests/test_batch_bibtex.py            ← 单元 + 集成测试

修改文件
  app/services/bibtex_io.py             ← 抽出 parse_entries / import_single_entry
  app/services/file_io.py（新）          ← 容纳从 documents.py 抽出的 _save_uploaded_files
  app/blueprints/documents.py           ← 改为从 file_io 导入
  app/templates/documents/list.html     ← 顶部加「批量识别 PDF」按钮
  app/blueprints/__init__.py            ← 注册新 Blueprint
```

**关键设计原则**

- 服务端三个端点都是**单篇粒度**的：识别一篇、入库一篇。"批量"语义完全由前端 JS 实现
- 服务端**无新增持久化状态**、**无新数据库表**、**无临时目录**、**无清理任务**
- 单次批量上限 **20 篇**（前端校验；服务端不强制）
- 前端识别和入库均**串行**（一个请求返回后才发下一个），避免重复并发与 MinerU 过载

## UI 设计

### 入口

`app/templates/documents/list.html` 顶部按钮区，原本是：

```html
<a class="btn btn-primary" href="{{ url_for('documents.new') }}">新增文献</a>
<a class="btn btn-outline-secondary" href="{{ url_for('bibtex.import_form') }}">导入 BibTeX</a>
```

新增第三个按钮：

```html
<a class="btn btn-outline-secondary" href="{{ url_for('batch_bibtex.batch_page') }}">批量识别 PDF</a>
```

### 批量页两态

**状态 0 · 空（未选文件）**

```
┌─ 顶部 ───────────────────────────────────────────────────────┐
│  批量识别 PDF + 批量入库                       [返回文献库]    │
└──────────────────────────────────────────────────────────────┘
┌───────────────────────────────────────────────────────────────┐
│   拖入或点击选择多个 PDF（上限 20 篇）                          │
│   [选择文件]   默认分类：[下拉] (可选)                          │
│   提示：识别期间不要关闭浏览器；.bib 草稿会本地保存             │
└───────────────────────────────────────────────────────────────┘
```

**状态 1 · 识别 + 填写（双栏）**

```
┌─────────────┬───────────────────────────────────────────────┐
│ 左：文件列表 │  右：分屏面板                                  │
│             │ ┌──────────────┬────────────────────────────┐ │
│ ✔ paper1.pdf│ │ markdown 渲染│ .bib 输入框                 │ │
│ ⟳ paper2.pdf│ │ (识别完成)   │ 空白模板（@article{,...}）   │ │
│ … paper3.pdf│ │              │ [格式校验提示]              │ │
│ ✘ paper4.pdf│ │              │                            │ │
│             │ └──────────────┴────────────────────────────┘ │
│ [重识别失败] │                                              │
│ [提交全部 ✓] │  (未选篇目时显示「请在左侧点击一篇开始」)      │
└─────────────┴───────────────────────────────────────────────┘
状态图标：⟳ 排队/识别中  ✔ 已识别  ✘ 失败  ● 已填写  ✓ 已入库
```

### 前端状态机

```
[选择 N 个 PDF]
   │
   ▼
[入队 → 串行调用 /bibtex/batch/recognize]
   │
   ├─ 成功 → 该篇状态 ✔，markdown 存 JS 内存（不写 localStorage）
   ├─ 失败 → 该篇状态 ✘，错误信息显示在列表项上，「重识别失败」按钮可一键重试所有 ✘
   │
[用户在右侧填 .bib，500ms 防抖写 localStorage]
   │
[点「提交全部」]
   │
   ▼
[串行调用 /bibtex/batch/import]
   │
   ├─ 已 ✘ 或 .bib 留空的 → 标记跳过，不发请求
   ├─ 服务端入库成功 → 该篇状态 ✓
   ├─ 服务端入库失败 → 该篇标 ✘ 入库失败，错误展示
   │
[汇总条：N 成功 / M 跳过 / K 失败，链接到 /documents]
   │
[localStorage 清理：成功入库项清掉草稿；失败/跳过保留]
```

### UI 细节

- **localStorage key**：以 `(filename, fileSize, lastModified)` 三元组 hash 作 key（如 `batchbib:<hash>`）。新批次开始时不主动清理；进入页面时清理 7 天前的旧 key
- **离开提醒**：未提交且有非空 `.bib` 时，`beforeunload` 弹"未提交的内容已保存在本地草稿"提示
- **markdown 渲染**：用 `marked.js`（约 30KB，UMD 版从 CDN 引或下载到 `/static/vendor/`）。仅在用户切换到该篇时才渲染，长度 >200KB 时不渲染只显示原文 + "原文过长"提示
- **`.bib` 格式提示**：textarea 下方一行实时反馈——"已识别为 1 个条目：article / 标题: ..."或"解析失败：..."。前端轻量正则校验，重的校验留给后端
- **进入页时 MinerU 健康检查**：调一次 `/health`（复用 `mineru_client.health_check`），失败则页面顶部红条提示「MinerU 未连接：请在 设置 中配置」并禁用上传

## 后端接口

### 接口 1：`GET /bibtex/batch` → `batch_bibtex.batch_page`

- `@login_required`
- 渲染 `bibtex/batch.html`，模板里需提供 `categories`（用户的分类列表，用于默认分类下拉）和 `mineru_url`（用于前端预先 health check）

### 接口 2：`POST /bibtex/batch/recognize` → `batch_bibtex.recognize`

- `@login_required`
- 请求 `multipart/form-data`：`pdf`（必填，单文件）
- 响应：
  - `200 {ok: true, filename, markdown}` —— `markdown` 为 MinerU 返回的原始内容
  - `400 {ok: false, error}` —— 未上传 / 不是 PDF / 文件为空
  - `502 {ok: false, error}` —— MinerU 调用失败（`MineruError` 转化）
- 实现：复用 `mineru_client.parse_pdf`，**不**调用 `pdf_metadata.extract_metadata`，**不**返回 `suggested_fields`。MinerU URL 取用户 `UserSetting.mineru_url`，缺省 `http://127.0.0.1:8000`（与 `recognize_pdf` 一致）

### 接口 3：`POST /bibtex/batch/import` → `batch_bibtex.import_one`

- `@login_required`
- 请求 `multipart/form-data`：
  - `pdf`（必填，单文件，作为附件）
  - `bib_text`（必填，应解析为恰好 1 个 entry）
  - `category_id`（可选，整数）
- 响应（注意：业务失败也返回 200，让前端按 `ok` 字段判别）：

| 场景 | 状态码 | 响应体 |
|---|---|---|
| 成功 | 200 | `{ok: true, document_id, title}` |
| `.bib` 空 | 200 | `{ok: false, reason: "bib_empty"}` |
| `.bib` 解析失败 | 200 | `{ok: false, reason: "bib_parse_failed", error_detail}` |
| `.bib` 含多 entry | 200 | `{ok: false, reason: "bib_multi_entry", error_detail}` |
| 重复 | 200 | `{ok: false, reason: "duplicate", error_detail: "已存在文献 ID 38"}` |
| DB 保存失败 | 200 | `{ok: false, reason: "save_failed", error_detail}` |
| 文件类型不允许 / 未上传 PDF | 400 | `{ok: false, error}` |
| 网络/服务器异常 | 500 | （Flask 默认 500 页面） |

- 实现伪代码：

```python
@bp.route("/batch/import", methods=["POST"])
@login_required
def import_one():
    pdf = request.files.get("pdf")
    bib_text = (request.form.get("bib_text") or "").strip()
    category_id = request.form.get("category_id", type=int)

    if not pdf or not pdf.filename:
        return jsonify(ok=False, error="未上传 PDF"), 400
    if not _allowed_file(pdf.filename):
        return jsonify(ok=False, error="不允许的文件类型"), 400
    if not bib_text:
        return jsonify(ok=False, reason="bib_empty")

    try:
        entries = bibtex_io.parse_entries(bib_text)
    except Exception as e:
        return jsonify(ok=False, reason="bib_parse_failed", error_detail=str(e))
    if len(entries) != 1:
        return jsonify(ok=False, reason="bib_multi_entry",
                       error_detail=f"该输入框应只含 1 个条目，实际 {len(entries)} 个")

    try:
        result = bibtex_io.import_single_entry(entries[0], current_user.id, category_id)
    except Exception as e:
        db.session.rollback()
        return jsonify(ok=False, reason="save_failed", error_detail=str(e))

    if result["skipped_reason"]:
        return jsonify(ok=False, reason="duplicate",
                       error_detail=result["skipped_reason"])

    doc = result["created"]
    saved_paths: list[Path] = []
    try:
        saved_paths = file_io.save_uploaded_files(doc, [pdf], current_user.id)
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

## `bibtex_io` 必要重构

```python
# 新增（纯解析，无副作用）
def parse_entries(bib_text: str) -> list[dict]: ...

# 新增（单条入库内核：含查重 + upsert + Author/Keyword/Source）
def import_single_entry(
    entry: dict, user_id: int, category_id: int | None = None
) -> dict:
    """
    返回：{"created": Document|None, "skipped_reason": str|None}
    - skipped_reason 命中场景：缺标题、DOI 重复、(title, year) 重复
    - 不 commit；调用方负责 commit / rollback
    """

# 现有函数保持向后兼容（既有 /bibtex/import 入口不动）
def import_bibtex(bib_text: str, user_id: int) -> tuple[int, int]:
    entries = parse_entries(bib_text)
    created = skipped = 0
    for e in entries:
        r = import_single_entry(e, user_id)
        if r["created"]:
            created += 1
        else:
            skipped += 1
    db.session.commit()
    return created, skipped
```

`import_single_entry` 实现要点：
- 直接搬现 `import_bibtex` 循环体内的全部逻辑，但参数化 `category_id`
- 查重命中时返回 `skipped_reason = f"已存在文献 ID {existing.id}"` 而不是单纯 `True`
- 不调用 `db.session.commit()`，由调用方决定事务边界

## `_save_uploaded_files` 抽离

当前位于 `app/blueprints/documents.py` line 81–104。把它原样搬到 `app/services/file_io.py`：

```python
# app/services/file_io.py
from pathlib import Path
import uuid
from flask import current_app
from werkzeug.utils import secure_filename

from ..extensions import db
from ..models import File


def save_uploaded_files(document, files, user_id) -> list[Path]:
    """保存附件文件到磁盘并建 File 记录。返回实际写入磁盘的路径列表，
    方便调用方在 commit 失败时回滚清理。"""
    upload_root = Path(current_app.config["UPLOAD_FOLDER"])
    user_dir = upload_root / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    allowed = current_app.config["ALLOWED_EXTENSIONS"]

    for f in files:
        if not f or not f.filename:
            continue
        ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
        if ext not in allowed:
            continue  # 调用方应已校验；此处保底
        original = secure_filename(f.filename) or "file"
        stored = f"{uuid.uuid4().hex}.{ext}"
        target = user_dir / stored
        f.save(target)
        saved.append(target)
        db.session.add(File(
            document_id=document.id,
            file_path=str(Path(str(user_id)) / stored).replace("\\", "/"),
            original_name=original,
            file_size=target.stat().st_size,
            mime_type=f.mimetype or "",
        ))
    return saved
```

`documents.py` 改为从 `file_io` 导入；既有行为（flash 警告"跳过不允许的文件类型"）由 documents 的调用层负责，新函数本身只静默跳过——批量场景不需要 flash。

## 错误处理矩阵

### 识别阶段

| 触发场景 | 服务端 | 前端表现 | 用户可选动作 |
|---|---|---|---|
| MinerU 未启动/连不上 | 502, `MineruError` 文案 | 该篇标 ✘，错误条提示"点 [重试] 或检查 MinerU 设置" | 重试该篇 / 跳到设置页 |
| MinerU 解析超时 | 502 | 同上 | 重试 |
| PDF 损坏/空文件 | 400 | 该篇标 ✘，提示"文件不是有效 PDF" | 删除该项 |
| 非 PDF 扩展名 | 前端 accept 过滤；服务端 400 兜底 | 不会出现 | — |
| 浏览器在识别中刷新 | 队列丢失；markdown 内存丢 | 重进页面是空状态 | 重新选 PDF；`.bib` 草稿自动恢复 |

### 填写阶段

| 场景 | 处理 |
|---|---|
| 用户清空整篇 `.bib` | 不报错，提交时按"跳过 - bib_empty"处理 |
| 用户粘多个 entry | 服务端返回 `bib_multi_entry`，前端在 textarea 下红字提示，提交时跳过 |
| 用户填的 `.bib` 缺 title | 服务端按"skipped_reason=缺标题"返回，前端按"跳过"显示 |
| 浏览器关闭 | localStorage 按文件 hash 分键的 `.bib` 草稿；同一 PDF 重传时自动恢复 |
| localStorage 配额溢出 | catch QuotaExceededError，弹一次"草稿保存失败"提示，不阻塞填写 |

### 入库阶段

见上文「接口 3」响应表。关键风险点：

- **附件孤儿**：`save_uploaded_files` 返回 `saved_paths` 列表；调用方 commit 失败时必须 unlink 已写入文件（伪代码已示）
- **重复检测**：沿用现有 `import_bibtex` 的"跳过+提示"语义，不覆盖已有

### 并发与幂等

- 前端入库阶段**串行**（一次只发 1 个请求），避免重复
- "提交全部"按钮按下后立即 disable，本轮完成后变成"重试失败项"
- 同一篇若已成功创建 Document，第二次相同请求被查重逻辑判为 duplicate，幂等

## 测试策略

### 单元测试（`tests/test_batch_bibtex.py`）

针对重构后的 `bibtex_io` 内核：

- `test_parse_entries_single` —— 单 entry 正确解析
- `test_parse_entries_empty` —— 空字符串返回 `[]`
- `test_parse_entries_multi` —— 多 entry 返回长度 >1
- `test_parse_entries_malformed` —— 缺 `}` / 缺 `@type` 抛异常
- `test_import_single_entry_creates` —— 新 entry 创建 Document、Author、Source、Keyword
- `test_import_single_entry_skips_duplicate_by_doi` —— 同 DOI 命中返回 `skipped_reason`
- `test_import_single_entry_skips_duplicate_by_title_year` —— 无 DOI 时回退到 (title, year)
- `test_import_single_entry_missing_title` —— 无标题返回 skipped
- `test_import_single_entry_with_category` —— `category_id` 正确设置
- `test_import_bibtex_backward_compatible` —— 旧 API 行为不变

### 集成测试

- `test_batch_page_requires_login`
- `test_batch_page_renders` —— 含分类下拉、含 mineru_url
- `test_batch_recognize_rejects_non_pdf`
- `test_batch_recognize_empty_file`
- `test_batch_recognize_success` —— monkeypatch `mineru_client.parse_pdf`，断言返回 `ok=True`、`markdown` 非空、**无** `suggested_fields` 字段
- `test_batch_recognize_mineru_error` —— `parse_pdf` 抛 `MineruError`，断言 502
- `test_batch_import_creates_doc_and_attaches_pdf`
- `test_batch_import_empty_bib_returns_skip`
- `test_batch_import_multi_entry_bib_rejected`
- `test_batch_import_duplicate_skipped`
- `test_batch_import_duplicate_does_not_attach_pdf` —— 被判为 duplicate 时不向现有文献加附件，磁盘不留孤儿文件
- `test_batch_import_rollback_cleans_orphan_attachment` —— 让 commit 抛错，断言磁盘上不留 PDF
- `test_batch_import_with_category_id`

### 手工验证范围

- 前端 JS 状态机（识别队列、localStorage、提交队列） —— 浏览器 console + DevTools
- markdown 渲染表现 —— 长 / 短 PDF 各一篇
- 端到端 —— 起真实 `mineru-api`，3 篇 PDF 全流程

### 覆盖目标

- 后端新增/修改代码语句覆盖 ≥80%
- 三端点的"成功路径 + ≥2 个失败路径"都有用例

## 接受标准

1. 文献列表页有「批量识别 PDF」按钮，点击进入 `/bibtex/batch`
2. 在批量页能一次选择 ≤20 个 PDF，前端逐篇调识别接口；左侧列表实时显示每篇状态
3. 点击已识别篇目，右侧出现分屏：左 markdown、右 `.bib` 输入框
4. `.bib` 输入有 localStorage 草稿；刷新页面、重新上传同一 PDF 后能恢复填写过的 `.bib`
5. 点「批量提交」逐条入库；成功的 PDF 作为附件挂到对应 Document；失败的展示原因并保留草稿可重提
6. 批量提交不会破坏 `bibtex_io.import_bibtex` 既有 API 的行为；`/bibtex/import` 文本批量入口照常工作
7. 重构后 `app/blueprints/documents.py` 的单篇上传 / 单篇识别功能均不回归
8. 失败回滚不留下孤儿附件文件
9. 后端测试覆盖：见「测试策略」节
