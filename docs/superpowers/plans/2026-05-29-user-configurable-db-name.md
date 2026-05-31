# 用户可配置数据库名称 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在桌面版设置页里增加「数据库连接」区块，让用户在应用内修改 MySQL 连接（含数据库名），保存后通过重启生效。

**Architecture:** 抽取 `desktop_app.py` 的连接逻辑到新模块 `app/services/db_config.py`，由首次向导和新增的设置页路由共享。设置页提供「测试连接」和「保存并重启」两个端点；保存成功后提示用户手动关闭并重新打开应用。

**Tech Stack:** Flask + Flask-Login + SQLAlchemy + pymysql + pywebview；测试用 pytest + monkeypatch。

**Spec:** `docs/superpowers/specs/2026-05-29-user-configurable-db-name-design.md`

---

## File Structure

| File | Role |
|------|------|
| `app/services/db_config.py` | **新建** — MySQL 配置的纯函数模块：校验、文件读写、连接测试、数据库创建 |
| `desktop_app.py` | 改：删本地等价函数，改为 import `db_config`，行为不变 |
| `app/blueprints/settings.py` | 改：注入 `db_cfg` 上下文 + 新增 `database_test` / `database_save` 路由 |
| `app/templates/settings/index.html` | 改：追加「数据库连接」卡片（`{% if db_cfg %}` 包住） + 一段独立 JS |
| `tests/test_db_config.py` | **新建** — 单元测试 `db_config.py` 的纯函数 |
| `tests/test_settings_database.py` | **新建** — 集成测试设置页 GET + 两个新路由 |

每文件单一职责：`db_config.py` 只管配置；`settings.py` 只管路由编排；模板只管渲染。`db_config.py` 不依赖 Flask，方便独立测试。

---

## Task 1: db_config 模块骨架 + 校验函数

**Files:**
- Create: `D:/GitHub项目/Personal_Library/app/services/db_config.py`
- Create: `D:/GitHub项目/Personal_Library/tests/test_db_config.py`

- [ ] **Step 1: 写失败的测试 — 校验函数**

写入 `tests/test_db_config.py`：

```python
import pytest

from app.services import db_config


class TestValidateDbName:
    def test_accepts_alphanumeric_and_underscore(self):
        assert db_config.validate_db_name("library_system") == "library_system"
        assert db_config.validate_db_name("MyDB_2") == "MyDB_2"

    def test_strips_surrounding_whitespace(self):
        assert db_config.validate_db_name("  lib  ") == "lib"

    def test_rejects_hyphen(self):
        with pytest.raises(ValueError, match="字母、数字、下划线"):
            db_config.validate_db_name("bad-name")

    def test_rejects_space_inside(self):
        with pytest.raises(ValueError, match="字母、数字、下划线"):
            db_config.validate_db_name("bad name")

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="字母、数字、下划线"):
            db_config.validate_db_name("")

    def test_rejects_too_long(self):
        with pytest.raises(ValueError, match="字母、数字、下划线"):
            db_config.validate_db_name("a" * 65)


class TestValidatePort:
    def test_accepts_int_in_range(self):
        assert db_config.validate_port(3306) == 3306
        assert db_config.validate_port("3306") == 3306
        assert db_config.validate_port(1) == 1
        assert db_config.validate_port(65535) == 65535

    def test_rejects_out_of_range(self):
        with pytest.raises(ValueError, match="1-65535"):
            db_config.validate_port(0)
        with pytest.raises(ValueError, match="1-65535"):
            db_config.validate_port(70000)

    def test_rejects_non_numeric(self):
        with pytest.raises(ValueError, match="1-65535"):
            db_config.validate_port("abc")
        with pytest.raises(ValueError, match="1-65535"):
            db_config.validate_port("")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd "D:/GitHub项目/Personal_Library" && python -m pytest tests/test_db_config.py -v`
Expected: 收集到 9 个测试，全部 FAIL（ImportError 或 AttributeError，因为模块/函数不存在）。

- [ ] **Step 3: 实现校验函数**

写入 `app/services/db_config.py`：

```python
"""共享 MySQL 配置模块：校验、文件读写、连接测试。

被 desktop_app.py（首次向导）和 settings 蓝图（应用内重设）共用。
本模块不依赖 Flask，便于独立测试。
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote_plus

APP_NAME = "PersonalLibrary"
_DB_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")


def validate_db_name(name: str) -> str:
    if not isinstance(name, str):
        raise ValueError("数据库名只允许字母、数字、下划线，长度 1-64")
    cleaned = name.strip()
    if not _DB_NAME_RE.fullmatch(cleaned):
        raise ValueError("数据库名只允许字母、数字、下划线，长度 1-64")
    return cleaned


def validate_port(port) -> int:
    try:
        value = int(port)
    except (TypeError, ValueError):
        raise ValueError("端口必须是 1-65535 的整数")
    if not (1 <= value <= 65535):
        raise ValueError("端口必须是 1-65535 的整数")
    return value
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_db_config.py -v`
Expected: 9 passed.

- [ ] **Step 5: 提交**

```bash
cd "D:/GitHub项目/Personal_Library"
git add app/services/db_config.py tests/test_db_config.py
git commit -m "feat(db_config): 数据库名/端口校验函数 + 单元测试"
```

---

## Task 2: db_config 文件路径与配置读写

**Files:**
- Modify: `D:/GitHub项目/Personal_Library/app/services/db_config.py`
- Modify: `D:/GitHub项目/Personal_Library/tests/test_db_config.py`

- [ ] **Step 1: 写失败的测试 — 文件路径与读写**

追加到 `tests/test_db_config.py`：

```python
class TestConfigFile:
    def test_appdata_dir_uses_app_name(self, monkeypatch, tmp_path):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        # 重新导入以避免模块级缓存影响（本项目里 appdata_dir 是函数调用，无缓存）
        d = db_config.appdata_dir()
        assert d == tmp_path / "PersonalLibrary"
        assert d.is_dir()

    def test_config_file_path_inside_appdata(self, monkeypatch, tmp_path):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        p = db_config.config_file_path()
        assert p == tmp_path / "PersonalLibrary" / "config.json"

    def test_config_file_exists_false_when_missing(self, monkeypatch, tmp_path):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        assert db_config.config_file_exists() is False

    def test_load_config_returns_none_when_missing(self, monkeypatch, tmp_path):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        assert db_config.load_config() is None

    def test_save_then_load_roundtrip(self, monkeypatch, tmp_path):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        cfg = {
            "host": "localhost",
            "port": 3306,
            "user": "root",
            "password": "secret",
            "database": "library_system",
            "secret_key": "deadbeef",
        }
        db_config.save_config(cfg)
        assert db_config.config_file_exists() is True
        assert db_config.load_config() == cfg

    def test_load_config_returns_none_on_invalid_json(self, monkeypatch, tmp_path):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        path = db_config.config_file_path()
        path.write_text("not json", encoding="utf-8")
        assert db_config.load_config() is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_db_config.py::TestConfigFile -v`
Expected: 6 个测试 FAIL（函数不存在）。

- [ ] **Step 3: 实现文件读写**

追加到 `app/services/db_config.py`：

```python
def appdata_dir() -> Path:
    """返回 %APPDATA%/PersonalLibrary（macOS/Linux 用对应路径），保证目录存在。"""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData/Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_file_path() -> Path:
    return appdata_dir() / "config.json"


def config_file_exists() -> bool:
    return config_file_path().exists()


def load_config() -> dict | None:
    p = config_file_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return None


def save_config(cfg: dict) -> None:
    config_file_path().write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_db_config.py -v`
Expected: 15 passed（含 Task 1 的 9 个）。

注意：Windows 下 `monkeypatch.setenv("APPDATA", ...)` 会被 `appdata_dir()` 读取；macOS/Linux 该测试会回退到 `Path.home() / "Library" / ...` 或 `~/.config`，跳过 APPDATA 路径。如果在非 Windows CI 上运行，前两条测试需要根据 `sys.platform` 分支判断 — 当前项目主要在 Windows 跑，先按原样写，如失败再修。

- [ ] **Step 5: 提交**

```bash
git add app/services/db_config.py tests/test_db_config.py
git commit -m "feat(db_config): appdata 路径与 config.json 读写 + 测试"
```

---

## Task 3: db_config MySQL 连接逻辑（mock pymysql）

**Files:**
- Modify: `D:/GitHub项目/Personal_Library/app/services/db_config.py`
- Modify: `D:/GitHub项目/Personal_Library/tests/test_db_config.py`

- [ ] **Step 1: 写失败的测试 — build_database_url / test_connection / ensure_database**

追加到 `tests/test_db_config.py`：

```python
class TestBuildDatabaseUrl:
    def test_basic(self):
        url = db_config.build_database_url({
            "user": "root", "password": "pwd", "host": "localhost",
            "port": 3306, "database": "library_system",
        })
        assert url == (
            "mysql+pymysql://root:pwd@localhost:3306/library_system?charset=utf8mb4"
        )

    def test_password_special_chars_url_encoded(self):
        url = db_config.build_database_url({
            "user": "root", "password": "p@ss/w?d", "host": "h",
            "port": 3306, "database": "db",
        })
        assert "p%40ss%2Fw%3Fd" in url


class TestTestConnection:
    def test_calls_pymysql_connect_with_cfg(self, monkeypatch):
        captured = {}

        class FakeConn:
            def close(self):
                captured["closed"] = True

        def fake_connect(**kwargs):
            captured.update(kwargs)
            return FakeConn()

        import pymysql
        monkeypatch.setattr(pymysql, "connect", fake_connect)
        db_config.test_connection({
            "host": "h", "port": 3307, "user": "u", "password": "p", "database": "d",
        })
        assert captured["host"] == "h"
        assert captured["port"] == 3307
        assert captured["user"] == "u"
        assert captured["password"] == "p"
        assert captured["closed"] is True

    def test_propagates_pymysql_error(self, monkeypatch):
        import pymysql

        def fake_connect(**kwargs):
            raise pymysql.err.OperationalError("denied")

        monkeypatch.setattr(pymysql, "connect", fake_connect)
        with pytest.raises(pymysql.err.OperationalError):
            db_config.test_connection({
                "host": "h", "port": 3306, "user": "u",
                "password": "p", "database": "d",
            })


class TestEnsureDatabase:
    def test_executes_create_database_if_not_exists(self, monkeypatch):
        executed = []

        class FakeCursor:
            def execute(self, sql):
                executed.append(sql)
            def __enter__(self): return self
            def __exit__(self, *a): return False

        class FakeConn:
            def cursor(self): return FakeCursor()
            def close(self): executed.append("CLOSED")

        import pymysql
        monkeypatch.setattr(pymysql, "connect", lambda **kw: FakeConn())
        db_config.ensure_database({
            "host": "h", "port": 3306, "user": "u",
            "password": "p", "database": "my_db",
        })
        sql_lines = [s for s in executed if "CREATE" in s]
        assert len(sql_lines) == 1
        assert "CREATE DATABASE IF NOT EXISTS `my_db`" in sql_lines[0]
        assert "utf8mb4" in sql_lines[0]
        assert "CLOSED" in executed
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_db_config.py -v`
Expected: TestBuildDatabaseUrl / TestTestConnection / TestEnsureDatabase 共 5 个 FAIL。

- [ ] **Step 3: 实现 MySQL 连接函数**

追加到 `app/services/db_config.py`：

```python
def build_database_url(cfg: dict) -> str:
    return (
        f"mysql+pymysql://{cfg['user']}:{quote_plus(cfg['password'])}"
        f"@{cfg['host']}:{cfg['port']}/{cfg['database']}?charset=utf8mb4"
    )


def test_connection(cfg: dict, timeout: float = 5.0) -> None:
    """仅尝试连接 MySQL 实例，不指定 database。失败抛 pymysql 异常。"""
    import pymysql

    conn = pymysql.connect(
        host=cfg["host"],
        port=int(cfg["port"]),
        user=cfg["user"],
        password=cfg["password"],
        charset="utf8mb4",
        connect_timeout=timeout,
    )
    conn.close()


def ensure_database(cfg: dict) -> None:
    """连接 MySQL 实例并执行 CREATE DATABASE IF NOT EXISTS。"""
    import pymysql

    conn = pymysql.connect(
        host=cfg["host"],
        port=int(cfg["port"]),
        user=cfg["user"],
        password=cfg["password"],
        charset="utf8mb4",
        connect_timeout=5,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{cfg['database']}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        conn.close()
```

注意：`ensure_database` 用反引号包数据库名；同时由调用方保证名字通过 `validate_db_name` 校验（只含字母/数字/下划线），双重防御。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_db_config.py -v`
Expected: 20 passed。

- [ ] **Step 5: 提交**

```bash
git add app/services/db_config.py tests/test_db_config.py
git commit -m "feat(db_config): build_url/test_connection/ensure_database + 测试"
```

---

## Task 4: 重构 desktop_app.py 改用 db_config（行为不变）

**Files:**
- Modify: `D:/GitHub项目/Personal_Library/desktop_app.py`

- [ ] **Step 1: 替换 imports 与本地函数**

打开 `desktop_app.py`，做以下三处改动：

**a. 顶部 imports（保留必要部分，删除冗余）：**

把原来的：

```python
import json
import os
import secrets
import socket
import sys
import threading
from pathlib import Path
from urllib.parse import quote_plus

import webview
```

改为：

```python
import os
import secrets
import socket
import sys
import threading

import webview

from app.services.db_config import (
    appdata_dir,
    load_config,
    save_config,
    build_database_url,
    ensure_database,
)
```

（删 `json` `Path` `quote_plus`：现在都在 `db_config` 里用。）

**b. 删除本地函数：**

删掉 `desktop_app.py` 中以下完整函数定义（已迁移到 `db_config.py`）：
- `def appdata_dir()` 及其上下文（保留 `APP_NAME = "PersonalLibrary"` 上面紧邻的 `WINDOW_TITLE = ...`）
- `def load_config()`
- `def save_config(cfg)`
- `def ensure_database(cfg)`
- `def build_database_url(cfg)`

也删掉模块级常量 `CONFIG_FILE = appdata_dir() / "config.json"`（不再被本文件使用；设置页通过 `config_file_path()` 取）。

**c. 保留 `APP_NAME` 与 `UPLOAD_DIR` 的初始化：**

`APP_NAME = "PersonalLibrary"` 现在已经定义在 `db_config.py` 里，但 `desktop_app.py` 顶部仍可保留同名常量（供窗口标题等使用），或直接删掉本地的 `APP_NAME`。**为减少混淆，删掉本地 `APP_NAME`**，因为 `desktop_app.py` 中目前只在 `appdata_dir()` 里引用过它。

`UPLOAD_DIR = appdata_dir() / "uploads"` 与 `UPLOAD_DIR.mkdir(...)` 这两行**保留**（启动期 side effect）。

- [ ] **Step 2: 静态检查 — 模块可导入**

Run: `cd "D:/GitHub项目/Personal_Library" && python -c "import desktop_app; print(desktop_app.WINDOW_TITLE)"`
Expected: 打印 `Personal Library · 个人文献管理`，无 ImportError。

如果有 `ModuleNotFoundError: webview`：在虚拟环境内执行 `python -m pip install pywebview`，或临时把 `import webview` 注释掉只验证其他符号 — 注意不要把注释提交。

- [ ] **Step 3: 跑全部已有测试确保未破坏**

Run: `python -m pytest -q`
Expected: 全部 pass（包含 Task 1-3 的 20 + 既有测试）。

- [ ] **Step 4: 提交**

```bash
git add desktop_app.py
git commit -m "refactor(desktop_app): 抽取数据库配置逻辑到 app.services.db_config"
```

---

## Task 5: settings.index 注入 db_cfg 上下文 + 模板加「数据库连接」卡片

**Files:**
- Modify: `D:/GitHub项目/Personal_Library/app/blueprints/settings.py`
- Modify: `D:/GitHub项目/Personal_Library/app/templates/settings/index.html`
- Create: `D:/GitHub项目/Personal_Library/tests/test_settings_database.py`

- [ ] **Step 1: 写失败的测试 — GET 设置页渲染**

写入 `tests/test_settings_database.py`：

```python
"""集成测试：设置页里的「数据库连接」区块。

不连真实 MySQL：在每个用例里 monkeypatch `db_config` 的相关函数。
"""

import pytest

from app.services import db_config


def _login(client):
    client.post(
        "/auth/register",
        data={"username": "tester", "password": "pw123456", "password2": "pw123456"},
    )


def _mock_config_present(monkeypatch, cfg=None):
    """让设置页认为 config.json 存在且包含给定 cfg。"""
    default = {
        "host": "localhost", "port": 3306, "user": "root",
        "password": "secret", "database": "library_system",
        "secret_key": "deadbeef",
    }
    monkeypatch.setattr(db_config, "config_file_exists", lambda: True)
    monkeypatch.setattr(db_config, "load_config", lambda: cfg or default)


def _mock_config_absent(monkeypatch):
    monkeypatch.setattr(db_config, "config_file_exists", lambda: False)
    monkeypatch.setattr(db_config, "load_config", lambda: None)


class TestSettingsIndex:
    def test_renders_database_card_when_config_exists(self, client, monkeypatch):
        _login(client)
        _mock_config_present(monkeypatch)
        resp = client.get("/settings/")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "数据库连接" in body
        assert 'name="host"' in body
        assert 'name="port"' in body
        assert 'name="user"' in body
        assert 'name="password"' in body
        assert 'name="database"' in body
        # 预填值正确
        assert 'value="localhost"' in body
        assert 'value="library_system"' in body
        # 密码不回显
        assert "secret" not in body

    def test_hides_database_card_in_dev_mode(self, client, monkeypatch):
        _login(client)
        _mock_config_absent(monkeypatch)
        resp = client.get("/settings/")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert 'id="db-form"' not in body
        assert "DATABASE_URL" in body  # 开发模式提示文本
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_settings_database.py -v`
Expected: 2 个 FAIL（响应不含「数据库连接」字样）。

- [ ] **Step 3: 在 settings.py 注入 db_cfg + 添加占位路由**

编辑 `app/blueprints/settings.py`：

首先在顶部 import 区加：

```python
from ..services import db_config
```

把 `index` 函数改为：

```python
@bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    s = _get_or_create_settings()
    if request.method == "POST":
        s.mineru_url = (request.form.get("mineru_url") or "").strip() or DEFAULT_MINERU_URL
        db.session.commit()
        flash("设置已保存", "success")
        return redirect(url_for("settings.index"))

    db_cfg_view = None
    if db_config.config_file_exists():
        current = db_config.load_config() or {}
        db_cfg_view = {
            "host": current.get("host", ""),
            "port": current.get("port", 3306),
            "user": current.get("user", ""),
            "database": current.get("database", ""),
            # 故意不暴露 password
        }
    return render_template(
        "settings/index.html",
        settings=s,
        default_url=DEFAULT_MINERU_URL,
        db_cfg=db_cfg_view,
    )
```

并在文件末尾追加两条占位路由（Task 6/7 会替换为真实实现）。**必须先加这两条**，否则模板里的 `url_for("settings.database_test")` 渲染时会抛 `BuildError` → GET 返回 500：

```python
@bp.post("/database/test")
@login_required
def database_test():
    return jsonify(ok=False, error="not implemented")


@bp.post("/database")
@login_required
def database_save():
    return jsonify(ok=False, error="not implemented")
```

- [ ] **Step 4: 修改模板追加卡片**

编辑 `app/templates/settings/index.html`，在 `.col-md-7` 整列内、紧跟着 MinerU 卡片 `</div>` 之后、`.col-md-7` 的 `</div>` 之前，插入：

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
    {% else %}
    <div class="alert alert-info">
      开发模式下数据库配置由 <code>.env</code> 中的 <code>DATABASE_URL</code> 决定，此处不提供修改入口。
    </div>
    {% endif %}
```

并在文件末尾 `{% endblock %}` 之前、现有 `</script>` 之后，追加第二段 JS：

```html
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
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_settings_database.py -v`
Expected: 2 passed.

也跑全套 sanity：

Run: `python -m pytest -q`
Expected: 全部 pass。

- [ ] **Step 6: 提交**

```bash
git add app/blueprints/settings.py app/templates/settings/index.html tests/test_settings_database.py
git commit -m "feat(settings): 设置页注入 db_cfg 上下文 + 数据库连接卡片 UI"
```

---

## Task 6: `/settings/database/test` 真实实现

**Files:**
- Modify: `D:/GitHub项目/Personal_Library/app/blueprints/settings.py`
- Modify: `D:/GitHub项目/Personal_Library/tests/test_settings_database.py`

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_settings_database.py`：

```python
class TestDatabaseTestRoute:
    def _valid_form(self, **overrides):
        data = {
            "host": "localhost", "port": "3306", "user": "root",
            "password": "newpw", "database": "library_system",
        }
        data.update(overrides)
        return data

    def test_rejects_bad_db_name(self, client, monkeypatch):
        _login(client)
        _mock_config_present(monkeypatch)
        resp = client.post("/settings/database/test", data=self._valid_form(database="bad-name"))
        assert resp.status_code == 200
        j = resp.get_json()
        assert j["ok"] is False
        assert "字母、数字、下划线" in j["error"]

    def test_rejects_bad_port(self, client, monkeypatch):
        _login(client)
        _mock_config_present(monkeypatch)
        resp = client.post("/settings/database/test", data=self._valid_form(port="70000"))
        j = resp.get_json()
        assert j["ok"] is False
        assert "1-65535" in j["error"]

    def test_rejects_missing_host(self, client, monkeypatch):
        _login(client)
        _mock_config_present(monkeypatch)
        resp = client.post("/settings/database/test", data=self._valid_form(host=""))
        j = resp.get_json()
        assert j["ok"] is False
        assert "不能为空" in j["error"]

    def test_blank_password_uses_saved_password(self, client, monkeypatch):
        _login(client)
        _mock_config_present(monkeypatch, cfg={
            "host": "h", "port": 3306, "user": "u", "password": "OLD",
            "database": "library_system", "secret_key": "k",
        })
        captured = {}

        def fake_test_conn(cfg, timeout=5.0):
            captured.update(cfg)

        monkeypatch.setattr(db_config, "test_connection", fake_test_conn)
        resp = client.post(
            "/settings/database/test",
            data=self._valid_form(password=""),
        )
        assert resp.get_json() == {"ok": True}
        assert captured["password"] == "OLD"

    def test_connection_failure_returns_error(self, client, monkeypatch):
        _login(client)
        _mock_config_present(monkeypatch)
        monkeypatch.setattr(
            db_config, "test_connection",
            lambda cfg, timeout=5.0: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        resp = client.post("/settings/database/test", data=self._valid_form())
        j = resp.get_json()
        assert j["ok"] is False
        assert "boom" in j["error"]

    def test_requires_login(self, client, monkeypatch):
        _mock_config_present(monkeypatch)
        resp = client.post("/settings/database/test", data=self._valid_form())
        # 未登录被重定向到 /auth/login
        assert resp.status_code in (302, 401)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_settings_database.py::TestDatabaseTestRoute -v`
Expected: 5 个 FAIL（占位路由总是返回 `{ok: false, error: "not implemented"}`），1 个可能 pass（test_requires_login 取决于占位路由是否带 `@login_required`，应该 pass）。

- [ ] **Step 3: 替换占位路由 — 真实实现**

在 `app/blueprints/settings.py` 顶部 import 区加上：

```python
import secrets
```

替换 `database_test` 占位，并新增一个内部辅助：

```python
def _build_cfg_from_form(form) -> tuple[dict | None, str | None]:
    """从表单构造完整 cfg dict。校验失败返回 (None, errmsg)。
    密码留空时从已存 config.json 合并旧密码。"""
    host = (form.get("host") or "").strip()
    user = (form.get("user") or "").strip()
    raw_db = (form.get("database") or "").strip()
    if not host or not user or not raw_db:
        return None, "主机、用户名、数据库名不能为空"
    try:
        port = db_config.validate_port(form.get("port"))
    except ValueError as e:
        return None, str(e)
    try:
        database = db_config.validate_db_name(raw_db)
    except ValueError as e:
        return None, str(e)
    password = form.get("password") or ""
    if password == "":
        old = db_config.load_config() or {}
        password = old.get("password", "")
    return {
        "host": host, "port": port, "user": user,
        "password": password, "database": database,
    }, None


@bp.post("/database/test")
@login_required
def database_test():
    cfg, err = _build_cfg_from_form(request.form)
    if err:
        return jsonify(ok=False, error=err)
    try:
        db_config.test_connection(cfg)
    except Exception as e:
        return jsonify(ok=False, error=str(e))
    return jsonify(ok=True)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_settings_database.py -v`
Expected: 全部 pass（Task 5 的 2 个 + Task 6 的 6 个 = 8 个）。

- [ ] **Step 5: 提交**

```bash
git add app/blueprints/settings.py tests/test_settings_database.py
git commit -m "feat(settings): /database/test 真实校验与连接测试"
```

---

## Task 7: `/settings/database` save 路由 — 校验、写盘、保留 secret_key

**Files:**
- Modify: `D:/GitHub项目/Personal_Library/app/blueprints/settings.py`
- Modify: `D:/GitHub项目/Personal_Library/tests/test_settings_database.py`

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_settings_database.py`：

```python
class TestDatabaseSaveRoute:
    def _valid_form(self, **overrides):
        data = {
            "host": "h", "port": "3306", "user": "u",
            "password": "newpw", "database": "lib",
        }
        data.update(overrides)
        return data

    def _mock_db_ok(self, monkeypatch):
        monkeypatch.setattr(db_config, "test_connection", lambda cfg, timeout=5.0: None)
        monkeypatch.setattr(db_config, "ensure_database", lambda cfg: None)

    def test_save_writes_config_on_success(self, client, monkeypatch):
        _login(client)
        _mock_config_present(monkeypatch, cfg={
            "host": "old", "port": 3306, "user": "old", "password": "old",
            "database": "old", "secret_key": "KEEP_ME",
        })
        self._mock_db_ok(monkeypatch)
        saved = {}
        monkeypatch.setattr(db_config, "save_config", lambda cfg: saved.update(cfg))

        resp = client.post("/settings/database", data=self._valid_form())
        assert resp.get_json() == {"ok": True}
        assert saved["host"] == "h"
        assert saved["database"] == "lib"
        assert saved["password"] == "newpw"
        # secret_key 必须保留，否则用户重启后会话全部失效
        assert saved["secret_key"] == "KEEP_ME"

    def test_save_generates_secret_key_when_missing(self, client, monkeypatch):
        _login(client)
        _mock_config_present(monkeypatch, cfg={
            "host": "h", "port": 3306, "user": "u", "password": "p",
            "database": "lib",
            # 故意没有 secret_key
        })
        self._mock_db_ok(monkeypatch)
        saved = {}
        monkeypatch.setattr(db_config, "save_config", lambda cfg: saved.update(cfg))

        resp = client.post("/settings/database", data=self._valid_form())
        assert resp.get_json() == {"ok": True}
        assert isinstance(saved.get("secret_key"), str)
        assert len(saved["secret_key"]) >= 32

    def test_save_rejects_when_test_connection_fails(self, client, monkeypatch):
        _login(client)
        _mock_config_present(monkeypatch)
        monkeypatch.setattr(
            db_config, "test_connection",
            lambda cfg, timeout=5.0: (_ for _ in ()).throw(RuntimeError("denied")),
        )
        save_called = []
        monkeypatch.setattr(db_config, "save_config", lambda cfg: save_called.append(cfg))

        resp = client.post("/settings/database", data=self._valid_form())
        j = resp.get_json()
        assert j["ok"] is False
        assert "denied" in j["error"]
        assert save_called == []

    def test_save_rejects_bad_db_name(self, client, monkeypatch):
        _login(client)
        _mock_config_present(monkeypatch)
        self._mock_db_ok(monkeypatch)
        save_called = []
        monkeypatch.setattr(db_config, "save_config", lambda cfg: save_called.append(cfg))

        resp = client.post("/settings/database", data=self._valid_form(database="bad name"))
        j = resp.get_json()
        assert j["ok"] is False
        assert save_called == []

    def test_save_reports_oserror(self, client, monkeypatch):
        _login(client)
        _mock_config_present(monkeypatch)
        self._mock_db_ok(monkeypatch)

        def fake_save(cfg):
            raise OSError("disk full")

        monkeypatch.setattr(db_config, "save_config", fake_save)
        resp = client.post("/settings/database", data=self._valid_form())
        j = resp.get_json()
        assert j["ok"] is False
        assert "disk full" in j["error"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_settings_database.py::TestDatabaseSaveRoute -v`
Expected: 5 个 FAIL（占位路由仍返回 `not implemented`）。

- [ ] **Step 3: 替换 database_save 占位 — 真实实现**

在 `app/blueprints/settings.py` 里替换 `database_save`：

```python
@bp.post("/database")
@login_required
def database_save():
    cfg, err = _build_cfg_from_form(request.form)
    if err:
        return jsonify(ok=False, error=err)
    try:
        db_config.test_connection(cfg)
        db_config.ensure_database(cfg)
    except Exception as e:
        return jsonify(ok=False, error=str(e))
    old = db_config.load_config() or {}
    cfg["secret_key"] = old.get("secret_key") or secrets.token_hex(32)
    try:
        db_config.save_config(cfg)
    except OSError as e:
        return jsonify(ok=False, error=f"写入配置文件失败: {e}")
    return jsonify(ok=True)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_settings_database.py -v`
Expected: 全部 pass（共 13 个）。

跑全套 sanity：

Run: `python -m pytest -q`
Expected: 全套 pass。

- [ ] **Step 5: 提交**

```bash
git add app/blueprints/settings.py tests/test_settings_database.py
git commit -m "feat(settings): /database 保存路由 + 密码/secret_key 合并测试"
```

---

## Task 8: 端到端冒烟（手动）+ 收尾

**Files:**
- 无新文件，仅运行验证

- [ ] **Step 1: 跑全套测试确认无回归**

Run: `cd "D:/GitHub项目/Personal_Library" && python -m pytest -q`
Expected: 全部 pass，无 deprecation/warning 暴增。

- [ ] **Step 2: 桌面版手动冒烟（需要本机 MySQL）**

如果本机没启动 MySQL，跳过本步并在 PR 描述里注明"未手动验证桌面流程"。

如果有 MySQL：

1. 删除 `%APPDATA%\PersonalLibrary\config.json`（或备份）。
2. Run: `python desktop_app.py`。
3. 在首次向导里填入有效连接信息，确认能进入主界面（验证 Task 4 refactor 没破坏向导）。
4. 进入 `/settings`，确认看到「数据库连接」卡片，5 个字段预填正确，密码框为空。
5. 把 `database` 改为新名称（如 `library_v2`），点「测试连接」→ 显示「连接成功」。
6. 点「保存并重启」→ 显示「已保存…」。
7. 关闭窗口，重新运行 `python desktop_app.py` → 验证现在连的是 `library_v2`（首次进入会自动建表，文档列表为空）。
8. 重复一次切回 `library_system`，确认旧数据还在。

- [ ] **Step 3: 开发模式手动冒烟**

1. Run: `python run.py`，访问 `http://127.0.0.1:5000/settings/`。
2. 注册/登录后进入设置页，确认 **不显示** 数据库连接卡片，而是看到「开发模式下…由 `.env` 中的 `DATABASE_URL` 决定」的提示。

- [ ] **Step 4: 末次提交（如有遗漏）+ 结束**

如果手动验证发现小问题（如文案、空格），现场修掉再 commit：

```bash
git add -p   # 选择性提交
git commit -m "fix(settings): 手动验证后微调"
```

否则本任务无新代码改动，跳过。

---

## 验收清单

- [ ] `app/services/db_config.py` 存在，含 9 个导出符号：`APP_NAME` / `validate_db_name` / `validate_port` / `appdata_dir` / `config_file_path` / `config_file_exists` / `load_config` / `save_config` / `build_database_url` / `test_connection` / `ensure_database`
- [ ] `desktop_app.py` 不再定义本地版本的上述函数
- [ ] `/settings/` GET 在桌面模式下渲染「数据库连接」卡片（5 个字段、密码不回显）
- [ ] `/settings/` GET 在开发模式下显示开发模式提示
- [ ] `/settings/database/test` POST：校验失败/连接失败/密码合并均行为正确
- [ ] `/settings/database` POST：校验失败/连接失败/写盘失败均不写 config.json；成功路径保留 `secret_key`
- [ ] `pytest -q` 全部 pass
- [ ] 桌面版手动冒烟：首次向导仍可用 + 设置页改名 + 重启切库可行（如无 MySQL，明确标注未验证）
