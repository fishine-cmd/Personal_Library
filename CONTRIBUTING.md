# 贡献指南

感谢你愿意为 Personal Library 项目贡献代码！本文档说明协作开发的规则与流程。

完整教程见 [`docs/协作开发指南.md`](docs/协作开发指南.md)。本文件是简要版。

---

## 快速开始

### 1. 准备本地环境

```bash
# 克隆
git clone https://github.com/fishine-cmd/Personal_Library.git
cd Personal_Library

# 创建虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # PowerShell
pip install -r requirements.txt

# 配置 .env（不要提交此文件）
copy .env.example .env
# 编辑 .env，填入本地 MySQL 信息和 FLASK_SECRET_KEY

# 创建数据库
# 在 MySQL 客户端执行:
# CREATE DATABASE library_system CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

# 跑起来
python run.py
# 浏览器打开 http://127.0.0.1:5000
```

### 2. 跑测试

```bash
pytest
```

---

## 开发流程

> **`main` 分支受保护，禁止直接推送。** 所有改动都必须走 Pull Request。

```bash
# 1. 同步 main
git checkout main && git pull

# 2. 开 feature 分支
git checkout -b feat/your-feature-name

# 3. 改代码 → 提交（多次 commit 都可以）
git add <file>
git commit -m "feat: 你做了什么"

# 4. 推到远端
git push -u origin feat/your-feature-name

# 5. 在 GitHub 上发 PR，等评审

# 6. 合并后清理
git checkout main && git pull
git branch -d feat/your-feature-name
```

---

## 命名约定

### 分支前缀

| 前缀 | 用途 |
|------|------|
| `feat/` | 新功能 |
| `fix/` | 修 bug |
| `refactor/` | 重构（不改行为） |
| `docs/` | 仅文档 |
| `test/` | 仅测试 |
| `chore/` | 杂项（依赖、配置等） |

格式：**`类型/短描述-用连字符`**，全小写英文。

### Commit Message

格式：`<类型>: <简短描述>`

```
feat: 新增 CSV 导出按钮
fix: 修复登录后跳转错误
refactor: 把 documents.py 的表单逻辑抽到 services
docs: 在 README 加快速上手段落
test: 补充 BibTeX 解析的边界用例
chore: 升级 Flask 到 3.0
```

---

## Pull Request 要求

每个 PR 必须说清楚：

1. **做了什么**（What）
2. **为什么这样做**（Why）—— 最重要
3. **怎么测**（How to test）
4. **截图**（如果是 UI 改动）

PR 模板会自动加载。

### PR 提交前自检

- [ ] 在本地跑过 `pytest`，全部通过
- [ ] 改 UI 的话，自己在浏览器里点过一遍
- [ ] commit message 符合上面的规范
- [ ] 一个 PR 只做一件事，不掺杂无关改动
- [ ] 没有提交 `.env`、`.venv/`、`__pycache__/` 等忽略文件

### Reviewer 要做的事

- 看代码是否符合既有架构（分层、Blueprint 划分、服务复用）
- 看是否有明显 bug、安全问题、性能坑
- 看 commit message、PR 描述是否清楚
- 看测试是否覆盖了改动
- 至少 1 个 Approve 才能合并

---

## 代码风格

- Python 部分按 PEP 8（缩进 4 空格、行长建议 ≤ 100）
- HTML/CSS/JS 缩进 2 空格
- 字符串优先用双引号 `"`
- 别留 `print(...)` 调试输出
- 编辑器请装 `.editorconfig` 插件，会自动统一行尾和缩进

---

## 报 bug / 提需求

→ 在 [Issues](https://github.com/fishine-cmd/Personal_Library/issues) 提交。

报 bug 时会自动加载模板，按提示填写复现步骤、预期/实际行为、环境信息。

---

## 不知道怎么开始？

1. 看 [README.md](README.md) 了解项目
2. 看 [docs/协作开发指南.md](docs/协作开发指南.md) 详细教程
3. 在 Issues 里挑一个标签为 `good first issue` 的开始
4. 不确定要不要改的地方，先开个 issue 讨论再动手
