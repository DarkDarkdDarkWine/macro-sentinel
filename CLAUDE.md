# Macro Sentinel

宏观哨兵 — 全球事件追踪 + 金融市场监控 + AI 驱动的投资建议系统。

## 技术栈

- Python 3.10+
- LLM：DeepSeek API（`deepseek-chat`）
- 市场数据：yfinance
- 新闻数据：GDELT / NewsAPI
- 部署：本地 + NAS Docker（amd64 / arm64）

## 目录结构

- `src/collectors/` — 数据采集（市场数据、新闻）
- `src/analyzers/` — AI 分析引擎（LLM 调用、信号生成）
- `src/reporters/` — 报告输出（格式化、推送）
- `src/models/` — 数据模型（Pydantic）
- `tests/` — 测试（镜像 src/ 结构）
- `scripts/` — 独立运行脚本（手动触发、调试用）

## 常用命令

- 安装依赖：`pip install -r requirements.txt`
- 运行：`python -m src.main`
- 测试：`pytest`
- Lint：`ruff check .`
- 格式化：`ruff format .`
- 类型检查：`mypy src/`

## 验证流程

每次改动后按顺序执行：
1. `mypy src/` — 修复类型错误
2. `pytest` — 修复失败的测试
3. `ruff check .` — 修复 lint 问题

## TDD

- 先写测试，再写实现，不接受没有测试覆盖的新功能
- 需求变更时，先更新测试用例，确认测试失败后，再开始修改实现
- 测试文件与源文件一一对应：`src/collectors/news.py` → `tests/collectors/test_news.py`
- 外部 API（DeepSeek、yfinance、NewsAPI）一律 mock，不在测试中发真实请求
- 每个测试只测一件事，测试名称说清楚场景：`test_fetch_vix_returns_float_on_success`
- 功能编写完成后必须运行 `pytest` 确认全部通过才算完成，发现失败自动定位原因并修复，不等用户指出

## 约定

- 所有数据结构用 Pydantic 模型定义
- LLM 调用统一封装在 `src/analyzers/llm.py`，不在其他地方直接调用 DeepSeek API
- 外部 API 调用加超时和重试，默认超时 30s
- 敏感配置（API Key 等）通过环境变量读取，参考 `.env.example`
- 日志用标准库 `logging`，不用 `print`

## AI 可读性

代码将由其他 AI 进行审阅，必须保持高可读性和可扩展性：

- 所有函数和类加 docstring，说明职责、参数、返回值和异常
- 全量类型注解，包括函数签名和局部变量
- 用具名常量替代魔法数字和魔法字符串
- 每个函数只做一件事，超过 40 行考虑拆分
- 模块边界清晰，依赖方向单一（collectors → analyzers → reporters），不反向依赖
- 复杂逻辑用注释解释"为什么"，而不是"做了什么"

## 新闻信源原则

新闻内容存在媒体立场偏差，采集和分析时必须注意：

- 同一事件必须覆盖东西方视角（如：Reuters/AP + 新华社/CGTN）
- Prompt 中明确要求 LLM 标注信息来源的可能立场，区分事实陈述和观点判断
- 市场数据（价格、利率、指标）是客观的；新闻只用来解释背景，不单独作为预测依据
- 不因信源立场过滤内容，让 LLM 综合多方视角后输出结论

## 禁止

- 不硬编码 API Key
- 不在 collectors 层做分析逻辑，只做数据获取
- 不捕获裸 `Exception`，捕获具体异常类型

## 自我改进

每次用户纠正错误或调整方向后，主动更新本文件中的相关约定，避免下次重复同样的问题。

## 提交规范

每次 git commit 前，必须同步更新 README.md，确保开发进度、已完成功能、使用方式与代码保持一致。
