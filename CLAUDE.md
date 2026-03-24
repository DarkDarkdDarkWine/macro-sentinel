# Macro Sentinel

宏观哨兵 — 全球事件追踪 + 金融市场监控 + AI 驱动的投资建议系统。

## 技术栈

Python 3.10+ / FastAPI / DeepSeek（`deepseek-chat`）/ yfinance / FRED / GDELT
部署：本地 + NAS Docker（amd64 / arm64）

## 目录结构

`src/collectors/` 采集 · `src/analyzers/` 分析 · `src/reporters/` 报告 · `src/models/` Pydantic 模型
`tests/` 镜像 src/ 结构 · `scripts/` 独立脚本

## 工作流触发

| 场景 | 使用技能 |
|------|---------|
| 新功能 >2 文件 | `superpowers:writing-plans` → 确认后再编码 |
| 实现阶段 | `superpowers:test-driven-development`（Red-Green-Refactor，Iron Law 无例外）|
| 任何 bug / 测试失败 | `superpowers:systematic-debugging`（先找根因，禁止猜测修复）|
| 宣布完成前 | `superpowers:verification-before-completion`；顺序：`mypy src/` → `pytest` → `ruff check .` |
| 功能完成后 | `superpowers:requesting-code-review` |
| 多个独立任务 | `superpowers:dispatching-parallel-agents` |

项目 TDD 补充：测试文件与源文件一一对应（`src/X.py` → `tests/X.py`）；外部 API 一律 mock。

## 约定

- 所有数据结构用 Pydantic 模型定义
- LLM 调用统一封装在 `src/analyzers/llm.py`，不在其他地方直接调用 DeepSeek API
- 外部 API 调用加超时（30s）和重试；敏感配置通过环境变量；日志用 `logging`

## AI 可读性

代码将由其他 AI 审阅：所有函数/类加 docstring；全量类型注解；具名常量替代魔法值；
函数超过 40 行考虑拆分；依赖方向单一（collectors → analyzers → reporters，不反向）。

## 新闻信源原则

- 同一事件必须覆盖东西方视角（Reuters/AP + 新华社/CGTN）
- Prompt 中要求 LLM 标注信源立场，区分事实与观点
- 市场数据是客观的；新闻只用来解释背景，不单独作为预测依据

## UI 设计

参考彭博终端（信息密度）+ 苹果股市 App（中英混排）；完整上下文见 `.impeccable.md`。
色彩只说事实：红=涨/危险，绿=跌/安全（中国市场习惯）；结论前置；圆角≤12px；无意义动效禁止。

## 禁止

不硬编码 API Key · 不在 collectors 层做分析逻辑 · 不捕获裸 `Exception`

## 自我改进 & 提交规范

被用户纠正后主动更新本文件相关约定；每次 commit 前同步更新 README.md。
