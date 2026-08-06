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

## 当前状态

单文件 HTML 原型已跑通（3D 图谱、节点标签、主题切换、数据流高亮、双击钻取），内嵌一个 voice-agent 示例项目数据（`audio_in → asr → llm → tts → audio_out` 全链路）。

下一步：把静态骨架接上真实 Python 解析、叠加运行时轨迹。

## 目录结构

```
.scratch/flowsight/
  prototype/        # 3D 原型（index.html + lib/ 引擎）
  research/         # 调研笔记（图可视化、Python 原语、技术景观）
  issues/           # wayfinder 工单（01–08）
  map.md            # wayfinder 决策追踪
doc/
  handoff/          # 阶段交接文档
  picture/          # 截图
```

## 运行原型

直接用浏览器打开 `.scratch/flowsight/prototype/index.html`（ESM 路径需联网加载 esm.sh；离线时自动回退本地 `lib/` 下的 UMD 引擎）。
