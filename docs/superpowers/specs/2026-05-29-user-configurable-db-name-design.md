# 用户可配置数据库名称 — 设计文档

- 日期：2026-05-29
- 范围：Personal Library 桌面版（desktop_app.py 启动路径）
- 状态：待用户审阅

## 1. 背景与目标

当前桌面版首次启动会弹出向导，让用户填写 MySQL 主机/端口/用户名/密码/**数据库名**，写入 `%APPDATA%\PersonalLibrary\config.json`。要改名只能手动删除该文件，重新走向导。

本次目标：**保留首次向导不变**，并在应用内的「设置」页中增加一个「数据库连接」区块，允许用户在已运行的应用里编辑当前连接配置（含数据库名），保存后通过重启生效。

不在范围：多库切换、历史库列表、数据迁移、应用内热重启、开发模式（`run.py`）下的 UI 改动。

## 2. 架构

### 2.1 公共模块抽取

把 `desktop_app.py` 现有的连接相关函数提到新模块 `app/services/db_config.py`，由首次向导和设置页共享。

```
desktop_app.py （首次向导 / 启动）──┐
                                     ├──► app/services/db_config.py
app/blueprints/settings.py        ──┘   - APP_NAME 常量
（设置页保存 / 测试连接）                - appdata_dir()
                                          - config_file_path()
                                          - config_file_exists()
                                          - load_config() / save_config(cfg)
                                          - build_database_url(cfg)
                                          - ensure_database(cfg)
                                          - test_connection(cfg)        # 新增
                                          - validate_db_name(name)      # 新增
                                          - validate_port(port)         # 新增
```

`desktop_app.py` 改为 `from app.services.db_config import ...`，删掉本地等价函数。行为保持完全一致。

### 2.2 设置页路由（settings.py）

| 方法 | 路径 | 行为 |
|------|------|------|
| GET  | `/settings/` | 渲染设置页，注入当前 MinerU 设置 + 当前 DB 配置（不含密码） |
| POST | `/settings/` | 保存 MinerU URL（既有功能，不动） |
| POST | `/settings/database/test` | 仅测试连接，不写盘，返回 `{ok, error?}` |
| POST | `/settings/database` | 校验 → 测试 → ensure_database → 写 `config.json`，返回 `{ok, error?}` |

两个 POST 路由均 `@login_required`。

## 3. 模块详细设计

### 3.1 `app/services/db_config.py`

```python
APP_NAME = "PersonalLibrary"
DB_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")

def appdata_dir() -> Path: ...
def config_file_path() -> Path: ...
def config_file_exists() -> bool: ...
def load_config() -> dict | None: ...
def save_config(cfg: dict) -> None: ...

def build_database_url(cfg: dict) -> str: ...
def ensure_database(cfg: dict) -> None:  # CREATE DATABASE IF NOT EXISTS
def test_connection(cfg: dict, timeout: float = 5.0) -> None:
    """仅尝试 pymysql.connect；不创建数据库；失败抛 pymysql 异常。"""

def validate_db_name(name: str) -> str:
    """返回规整后的 name；非法时 raise ValueError('数据库名只允许字母、数字、下划线，长度 1-64')。"""

def validate_port(port: str | int) -> int:
    """返回 int(port)；非法时 raise ValueError。1 ≤ port ≤ 65535。"""
```

迁移要点：
- `appdata_dir / "uploads"` 这一行**留在 `desktop_app.py`**（属于启动期 side effect，不属于"配置"职责）。
- `secrets.token_hex(32)` 的密钥生成也留在 `desktop_app.py`，本模块不碰。

### 3.2 `app/blueprints/settings.py` 改动

```python
from ..services import db_config

@bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    # ... 现有 MinerU 逻辑保留 ...
    current_db = db_config.load_config() if db_config.config_file_exists() else None
    db_cfg_view = None
    if current_db:
        db_cfg_view = {
            "host": current_db.get("host", ""),
            "port": current_db.get("port", 3306),
            "user": current_db.get("user", ""),
            "database": current_db.get("database", ""),
            # 注意：故意不暴露 password
        }
    return render_template(
        "settings/index.html",
        settings=s,
        default_url=DEFAULT_MINERU_URL,
        db_cfg=db_cfg_view,                # None ⇒ 开发模式，不渲染卡片
    )

@bp.post("/database/test")
@login_required
def database_test():
    cfg, err = _build_cfg_from_form(request.form, merge_password=True)
    if err:
        return jsonify(ok=False, error=err)
    try:
        db_config.test_connection(cfg)
    except Exception as e:
        return jsonify(ok=False, error=str(e))
    return jsonify(ok=True)

@bp.post("/database")
@login_required
def database_save():
    cfg, err = _build_cfg_from_form(request.form, merge_password=True)
    if err:
        return jsonify(ok=False, error=err)
    try:
        db_config.test_connection(cfg)
        db_config.ensure_database(cfg)
    except Exception as e:
        return jsonify(ok=False, error=str(e))
    # 合并原 secret_key，避免重启后会话失效
    old = db_config.load_config() or {}
    cfg["secret_key"] = old.get("secret_key") or secrets.token_hex(32)
    try:
        db_config.save_config(cfg)
    except OSError as e:
        return jsonify(ok=False, error=f"写入配置文件失败: {e}")
    return jsonify(ok=True)

def _build_cfg_from_form(form, merge_password: bool) -> tuple[dict | None, str | None]:
    """从表单组装 cfg dict。校验失败返回 (None, errmsg)。密码空白时从旧 config.json 合并。"""
```

### 3.3 模板改动 `app/templates/settings/index.html`

在 MinerU 卡片之后追加：

```html
{% if db_cfg %}
<div class="card mb-3">
  <div class="card-header">数据库连接（MySQL）</div>
  <div class="card-body">
    <p class="text-muted small mb-3">
      修改后需 <strong>关闭并重新打开应用</strong> 才会生效。
      切换到不存在的数据库会自动新建；旧数据库的数据保留在原处。
    </p>
    <form id="db-form" class="row g-3">
      <div class="col-8">
        <label class="form-label">主机</label>
        <input class="form-control" name="host" value="{{ db_cfg.host }}" required>
      </div>
      <div class="col-4">
        <label class="form-label">端口</label>
        <input class="form-control" name="port" value="{{ db_cfg.port }}" required>
      </div>
      <div class="col-12">
        <label class="form-label">用户名</label>
        <input class="form-control" name="user" value="{{ db_cfg.user }}" required>
      </div>
      <div class="col-12">
        <label class="form-label">密码</label>
        <input type="password" class="form-control" name="password"
               placeholder="留空 = 保持现密码">
      </div>
      <div class="col-12">
        <label class="form-label">数据库名</label>
        <input class="form-control" name="database" value="{{ db_cfg.database }}" required>
        <div class="form-text">只允许字母、数字、下划线；不存在会自动创建。</div>
      </div>
      <div id="db-result" class="col-12"></div>
      <div class="col-12 d-flex gap-2">
        <button class="btn btn-outline-secondary" type="button" id="btn-db-test">测试连接</button>
        <button class="btn btn-primary" type="button" id="btn-db-save">保存并重启</button>
      </div>
    </form>
  </div>
</div>
<script>
(function () {
  const form = document.getElementById('db-form');
  if (!form) return;
  const out = document.getElementById('db-result');
  const postForm = async (url) => {
    const r = await fetch(url, { method: 'POST', body: new FormData(form) });
    return r.json();
  };
  const showResult = (cls, msg) => {
    out.innerHTML = `<div class="alert ${cls} py-2 mb-0">${msg}</div>`;
  };
  document.getElementById('btn-db-test').addEventListener('click', async () => {
    showResult('alert-info', '正在测试...');
    try {
      const j = await postForm('{{ url_for("settings.database_test") }}');
      showResult(j.ok ? 'alert-success' : 'alert-danger',
                 j.ok ? '连接成功' : '连接失败: ' + j.error);
    } catch (e) { showResult('alert-danger', '请求失败: ' + e); }
  });
  document.getElementById('btn-db-save').addEventListener('click', async () => {
    showResult('alert-info', '正在保存...');
    try {
      const j = await postForm('{{ url_for("settings.database_save") }}');
      if (j.ok) {
        showResult('alert-success', '已保存。请关闭窗口后重新打开应用以生效。');
      } else {
        showResult('alert-danger', '保存失败: ' + j.error);
      }
    } catch (e) { showResult('alert-danger', '请求失败: ' + e); }
  });
})();
</script>
{% else %}
<div class="alert alert-info">
  开发模式下数据库配置由 <code>.env</code> 中的 <code>DATABASE_URL</code> 决定，此处不提供修改入口。
</div>
{% endif %}
```

### 3.4 `desktop_app.py` 改动

```python
from app.services.db_config import (
    appdata_dir, load_config, save_config,
    build_database_url, ensure_database,
)
# 删除本地同名函数。其他逻辑（make_main_app/run_setup_wizard/SETUP_HTML/main）保持不变。
UPLOAD_DIR = appdata_dir() / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
```

## 4. 关键决策记录

1. **不做应用内热重启**：SQLAlchemy 连接池切换库会污染已有 session，pywebview 内重启 Flask 进程不优雅。改用"保存 → 提示用户关窗 → 下次启动读新配置"的简单可靠方案。
2. **密码不回显**：表单密码字段空白 = 保持旧密码，仅在用户明确填写时才覆盖。
3. **开发模式 (`run.py`) 不展示编辑卡片**：通过 `config_file_exists()` 判断，避免在 `.env` 流程下展示一个其实不生效的表单。
4. **保存路径强制先 test_connection**：避免把坏配置写入 `config.json` 导致下次启动直接挂。
5. **校验数据库名**：正则 `^[A-Za-z0-9_]{1,64}$`，既符合 MySQL 标识符规范，又规避了反引号/SQL 注入风险（`CREATE DATABASE` 语句用反引号包名，但额外校验是 defense-in-depth）。
6. **不做多库管理**：与用户明确选择一致（首次配置 + 重设，而非 EndNote 式多库切换）。

## 5. 错误处理

所有 POST 路由统一返回 `{ok: bool, error?: str}`。错误来源与提示：

| 来源 | 用户看到 |
|------|----------|
| `validate_db_name` 失败 | "数据库名只允许字母、数字、下划线，长度 1-64" |
| `validate_port` 失败 | "端口必须是 1-65535 的整数" |
| 必填字段为空 | "主机/用户名/数据库名不能为空" |
| pymysql 连接异常 | pymysql 异常 str |
| `CREATE DATABASE` 权限不足 | pymysql 异常 str |
| `save_config` OSError | "写入配置文件失败: …" |

## 6. 测试计划

新增 `tests/test_settings_database.py`：

- `test_settings_index_renders_db_card_when_config_exists`：mock `db_config.config_file_exists` 返回 True，mock `load_config` 返回完整 cfg，断言响应含 `name="database"` 字段且预填值正确，**不含密码原文**。
- `test_settings_index_hides_db_card_in_dev_mode`：mock `config_file_exists` 返回 False，断言响应含「开发模式」提示文本，不含 `id="db-form"`。
- `test_database_test_rejects_bad_name`：POST `database` 字段为 `bad-name`（含连字符），断言 `{ok: false, error: contains "字母、数字、下划线"}`。
- `test_database_test_rejects_bad_port`：POST `port=70000`，断言失败。
- `test_database_save_merges_password_when_blank`：mock `load_config` 返回 `{password: "old"}`，POST password 为空 → 断言传给 `test_connection`/`save_config` 的 cfg 含 `password: "old"`。
- `test_database_save_writes_config_on_success`：mock `test_connection`/`ensure_database` 不抛错，mock `save_config` 收到合并后的 cfg；断言响应 `{ok: true}` 且 `save_config` 被调用。
- `test_database_save_does_not_write_on_test_failure`：mock `test_connection` 抛错，断言 `save_config` 未被调用，响应 `ok=false`。

测试使用 SQLite 内存 + monkeypatch，无需真实 MySQL；登录态走现有 `tests/conftest.py` 的辅助（如已存在）或新增一个 fixture。

## 7. 文件改动清单

| 文件 | 动作 |
|------|------|
| `app/services/db_config.py` | 新建 |
| `app/blueprints/settings.py` | 修改：新增 2 路由 + db_cfg 上下文 |
| `app/templates/settings/index.html` | 修改：追加数据库卡片 + JS |
| `desktop_app.py` | 修改：import db_config，删本地同名函数 |
| `tests/test_settings_database.py` | 新建 |
| `docs/superpowers/specs/2026-05-29-user-configurable-db-name-design.md` | 本文件 |

## 8. 越界（明确不做）

- 多库切换 / 历史库列表
- 跨库数据迁移
- 应用内热重启 Flask 进程
- 开发模式（`run.py`）下的可视化配置入口
- `config.json` 的加密存储（password 当前已明文存在，本次不动）
