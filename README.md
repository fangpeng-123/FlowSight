# FlowSight

> 把一个 Python 代码库自动变成可交互的 3D 知识图谱——不用逐行读代码，就能看懂「结构、数据怎么流、接口契约、哪里有坑」。

## 解决什么问题

阅读障碍 / 代码量大时，逐行读源码效率低、抓不住全貌。FlowSight 用图替代文字，点开即钻取。

## 四个核心内容区

1. **核心数据结构** — dataclass / 结构体 + 字段
2. **接口契约** — 函数的 入参 / 返回 / 错误码 / 边界条件
3. **依赖图 + 数据流** — 谁调谁、数据在管道里怎么流转
4. **风险清单** — 高风险函数及规避建议

## 技术取向

- 仅 Python；LLM 驱动（用大模型理解语义，不只靠正则解析）
- **静态骨架 + 运行时轨迹** 混合：静态先搭结构，运行时 trace 叠加真实调用
- 3D 力导向图，单击选中、双击展开/收起层级
- 零运行时依赖的服务端（stdlib `http.server`），3D 引擎（three.js / d3-force）离线内置，无需联网

## 当前状态

核心 MVP（工单 01–05）已实现，60 个测试通过：

- **ticket 01** 骨架提取 — 用 Jedi 静态解析 Python 项目，产出「模块 / 文件 / 类 / 函数 / 外部依赖」图 JSON；模块 purpose 自动从 docstring 富化
- **ticket 02** 本地 3D 视图 — 服务端渲染力导向图（选中 / 双击钻取 / 主题切换）
- **ticket 03** LLM 富化 — 模块目的优先走 LLM，docstring 兜底；已用 `.flowsight/enrich-cache.json` 缓存
- **ticket 04** 领域实体 — dataclass 字段、函数签名、数据流角色建模
- **ticket 05** 运行时叠加 — viztracer 采集真实调用轨迹，叠加出 `data_flow` 边，静态图与运行时轨迹比对（divergence）

## 安装

需要 Python ≥ 3.11。

```bash
pip install -e ".[dev,runtime]"
```

`dev` 含 pytest；`runtime` 含 viztracer（仅 `trace` 命令需要）。

## 用法

```bash
# 1. 分析项目，输出图 JSON（Redis 到 stdout 或 -o 文件）
flowsight index <项目路径> -o graph.json

# 2. 启动 3D 知识图谱，浏览器自动打开 http://127.0.0.1:8000
flowsight serve <项目路径>
flowsight serve <项目路径> -p 9000 --no-browser
flowsight serve <项目路径> --trace <trace.json>   # 叠加运行时轨迹

# 3. 采集运行时轨迹并叠加数据流（ticket 05）
flowsight trace -- <script.py> <args> --project <项目路径>
flowsight trace -m <module> --project <项目路径>   # 用 `--` 分隔模块参数
flowsight trace --from <trace.json> --project <项目路径>   # 吃掉现成 trace
```

**示例**：分析内置示例项目，看到 `audio_in → asr → llm → tts → audio_out` 全链路：

```bash
flowsight serve tests/fixtures/voice_agent
```

## 目录结构

```
src/flowsight/
  cli.py                # 命令行入口（index / serve / trace）
  schema.py             # 图 JSON 领域模型
  skeleton/             # 静态骨架：Jedi 解析、引用解析、venv 探测
  enrich/               # LLM 富化：LLM 客户端、缓存、挂接
  overlay/              # 运行时叠加：viztracer 轨迹、相关器
  server/               # stdlib http.server：静态资源 + /api/graph + /api/enrich
  web/                  # 3D 图谱前端（app.js / 自适应 / 内置 3 台引擎）
tests/                  # pytest + 一个 voice_agent 夹具
  fixtures/             # voice_agent 示例项目 + trace.json
```

## 开发

```bash
python -m pytest        # 运行测试
```