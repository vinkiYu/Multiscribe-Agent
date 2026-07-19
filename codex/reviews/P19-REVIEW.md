# Review: P19-预置Skill系统

**执行包**：`docs/phases/P19-预置Skill系统.md`
**完成日期**：2026-07-19
**执行者**：Codex

## 1. 范围核对

| 文件路径 | 操作 | 用途 |
| :--- | :--- | :--- |
| `src/multiscribe_agent/skills/**` | 新增 | frontmatter parser、scanner、registry、service、loader |
| `src/multiscribe_agent/resources/skills/**/SKILL.md` | 新增 | 三个内置 Skill |
| `data/skills/.gitkeep` | 新增 | 自定义 Skill runtime 根目录 |
| `src/multiscribe_agent/api/routes/skills.py` | 新增 | JWT Skill API |
| `src/multiscribe_agent/agents/executor.py` | 修改 | 注入实际 Skill 摘要 |
| `src/multiscribe_agent/bootstrap.py` | 修改 | SkillService 启动加载 |
| `src/multiscribe_agent/app.py` | 修改 | 注册 skills router |
| `tests/skills/**` | 新增 | 12 项 parser/scanner/registry/service/builtin/API/executor 测试 |

实现未修改 P19 黑名单的 domain models、prompt service、prompt resources、plugin base、API deps/security、DB schema 或 entity JSON repository。

## 2. 验收条件逐条对照

| # | 验收条件 | 状态 | 证据 |
| :--- | :--- | :--- | :--- |
| 1 | frontmatter 解析/错误 | ✅ | parser 正常、block list、两种错误路径测试 |
| 2 | 递归扫描 | ✅ | `test_scanner_recursively_discovers_skill_documents` |
| 3 | custom 覆盖 builtin | ✅ | `test_load_all_allows_custom_skill_to_override_builtin` |
| 4 | 三个预置 Skill 自动注册 | ✅ | bootstrap `_init_skills()` 加载 resources 根；内置文件齐全 |
| 5 | executor 注入摘要 | ✅ | `test_executor_injects_loaded_skill_summary` 验证 name/instructions |
| 6 | 五个 JWT API | ✅ | `test_skill_api_crud_and_reload` 覆盖 401、list/get/create/reload/delete |
| 7 | 至少 12 测试 | ✅ | `tests/skills`: `12 passed` |
| 8 | 全量质量门绿 | ❌ | ruff/format/mypy 通过；全量 pytest 3 个 P16 失败 |
| 9 | 既有 205+ 无回归 | ❌ | 同上 |

## 3. 测试与质量门

```text
.venv\Scripts\python.exe -m pytest tests/skills -v -p no:cacheprovider --basetemp .pytest-tmp-skills
12 passed in 0.63s

ruff check .
All checks passed!

ruff format --check .
200 files already formatted

mypy src
Success: no issues found in 119 source files

pytest tests/memory tests/mcp tests/skills -q -p no:cacheprovider --basetemp .pytest-tmp-final
33 passed in 0.90s

pytest -q -p no:cacheprovider --basetemp .pytest-tmp-all
229 passed, 3 failed, 4 deselected in 25.64s
```

## 4. 详细任务完成情况

- **格式/扫描**：纯 Python 解析 `name`、`description`、inline/block `bins`，无 PyYAML；目录扫描在 worker thread 中运行。
- **生命周期**：自定义 Skill 覆盖同 id 内置 Skill；删除自定义 override 后恢复 builtin；id 正则拒绝路径穿越。
- **预置内容**：`tech-weekly`、`multi-source-compare`、`smart-recommendation` 已随 package 资源加载。
- **执行器/API**：executor 读取单例 registry，注入 name/description/instructions 前 1500 字符；API 使用既有 JWT。

## 5. 风险、遗留与取舍

- **阻塞风险**：P16 既有可选 runtime 造成全量 pytest 3 项失败，详见 P17/P18 Review；未越界修改其黑名单。
- **取舍**：SKILL.md frontmatter 只支持任务包定义的三字段，而非完整 YAML，以避免新增 PyYAML 依赖。
- **未做**：不向 executor 注入 SkillService 本身，仅读取 registry，保持 P19 指定依赖边界。

## 6. BLOCKED 项

- **阻塞点**：全量 pytest 未绿，故不能满足 P19 完成定义。
- **需要决策**：P16 独立修复可选依赖/测试假设后，重跑全量质量门。

## 7. 自评

- 功能验收与 12 项专项测试通过；由于硬质量门失败，本包完成定义：❌
