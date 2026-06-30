# Implementation Plan: Voyager ER 图 —— 关联实体侧边栏 Tab

**Branch**: `005-related-entities-tab` | **Date**: 2026-06-30 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-related-entities-tab/spec.md`

## Summary

在 Voyager ER 图的双击侧边栏中新增第三个 tab "Related Entities"。该 tab 渲染一张**只读的迷你 ER 子图**，内容为"所选实体 + 其直接关联实体 + 它们之间的边"，作为主图"高亮一层邻域"在侧边栏内的聚焦视图。子图**复用主图当前的渲染配置**（show module cluster / show methods / edge length），随主图配置或所选实体的变化自动重新渲染，本身不暴露任何配置项。

同时修复一处现有交互缺陷（spec FR-011/012/013）：侧边栏已打开时，画布上**单击**其他 entity 必须让侧边栏跟随更新（当前只有双击才更新）；切换实体时**保留**当前激活的 tab；在画布**空白处纯点击**关闭侧边栏，**拖拽**（平移视图）则不关闭。

**技术取舍（详见 [research.md](./research.md)）**：

- **子图数据来源**：新增后端接口 `POST /er-diagram-subgraph`，复用 `ErDiagramDotBuilder` 的全部渲染逻辑（show_module / show_methods / edge_minlen / show_fields / theme_color），邻域从权威的 `ErManager` 实体注册表计算。前端用一个新的 d3-graphviz 实例在 tab 内渲染返回的 DOT。客户端过滤方案被否决，原因是无法等价复用后端的 DOT 生成与样式逻辑（详见 R1）。
- **邻域一致性**：邻域从 `ErManager` 注册表计算（与主图同源），保证子图与主图对"直接关联"的语义完全一致；高亮（client-side）与子图（server-side）在无过滤时结果相同。
- **侧边栏跟随选择**：纯前端改动，在 `graph-ui.js` 的 `click` 处理器中，当侧边栏处于打开状态时额外触发 `onSchemaClick` 回调；FR-012（tab 保留）在现有代码中**已经成立**（`schema-code-display.js` 的 `resetState()` 已注释掉 tab 重置），只需保留并加测试。
- **空白点击 vs 拖拽**：在画布的 background click 路径上，复用现有 mousedown/mouseup 位移阈值判定手势。

## Technical Context

**Language/Version**: Python 3.10+（后端，`pyproject.toml` `requires-python = ">=3.10"`）；前端为浏览器内嵌的 ES module JS + Vue 3（全局构建，无打包步骤）+ Quasar + d3-graphviz + jQuery（沿用现有 `src/nexusx/voyager/web/` 技术栈）。

**Primary Dependencies**:
- 后端：`pydantic`、`sqlmodel`、`fastapi`（沿用现有 voyager HTTP 层）；`ErDiagramDotBuilder`（`src/nexusx/voyager/er_diagram_dot.py:77`）是本功能复用的核心。
- 前端：`d3-graphviz`（`index.html:658-664` 加载）、Vue 3 + Quasar（全局）、jQuery（`graph-ui.js` 用）。

**Storage**: N/A —— 子图不引入任何持久化；状态全部在内存（前端 store + 后端 `ErManager` 注册表）。

**Testing**:
- 后端：`pytest`（沿用 `tests/` 现有布局），为 `ErDiagramDotBuilder` 的邻域过滤与 `/er-diagram-subgraph` 端点加单元/集成测试。
- 前端：当前 web 目录无自动化测试基础设施；以**手动验证 + `quickstart.md` 场景**为主（与现有 voyager 前端一致），关键交互逻辑（手势判定、tab 保留、回调触发）尽量写成纯函数以便日后接入测试。

**Target Platform**: Linux / macOS / Windows 桌面浏览器（开发者本机，与现有 voyager 一致）。

**Project Type**: library（后端 `src/nexusx/`）+ 内嵌 web 前端（`src/nexusx/voyager/web/`，作为静态资源随 Python 包分发）。

**Performance Goals**:
- 子图 DOT 生成 < 50 ms（子图节点数 ≤ 主图，通常 ≤ 数十），HTTP 往返 + 渲染在用户感知为即时（spec SC-005）。
- 主图配置变化触发的子图重渲染不得阻塞主图自身的重渲染。
- 侧边栏跟随单击的更新必须在同一事件循环内完成 store 更新，不引入额外网络等待（仅 `schemaCodeName` 切换；子图 fetch 异步进行，加载态可见）。

**Constraints**:
- **不破坏现有 ER 图渲染**：`ErDiagramDotBuilder` / `/er-diagram` 行为不变，本功能是**追加**一条复用路径（spec 假设章节）。
- **不引入新的前端构建链**：前端仍是全局脚本 + ES module，不引入打包工具。
- **子图只读**：不在子图内启用实体选中/导航回调（spec FR-007/FR-016）。
- **手势判定不引入新机制**：click vs drag 复用画布现有的 mousedown/mouseup 位移逻辑（spec FR-013）。
- **Tab 保留行为不得回归**：`schema-code-display.js` 中 `resetState()` 注释掉的 `tab.value = "fields"` 必须保持注释状态（spec FR-012）。

**Scale/Scope**: 约 250–400 LOC：
- 后端：`er_diagram_dot.py` 加邻域过滤构造路径（~40 LOC）+ `create_voyager.py` 加 `/er-diagram-subgraph` 端点 + payload 模型（~50 LOC）+ 测试（~120 LOC）。
- 前端：新增 `related-entities-display.js` 组件（~120 LOC，d3-graphviz 渲染 + 加载/错误/空态）+ `vue-main.js` / `index.html` 注册组件与 tab（~30 LOC）+ `graph-ui.js` 改单击回调与空白点击关闭（~40 LOC）。

大致 2 个 PR：
1. 后端：子图 DOT 构造 + `/er-diagram-subgraph` 端点 + 后端测试。
2. 前端：新组件 + tab 注册 + 侧边栏跟随选择 + 空白点击关闭 + 手动验证。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Status**: N/A —— `.specify/memory/constitution.md` 仍是未填写的模板（10 个 `[PRINCIPLE_*]` 占位符未填）。没有可供 gate 的原则。Phase 1 设计完成后的再检查同样为 N/A，直到由独立的 `/speckit-constitution` 流程填写。

**Recommendation**: 不因 constitution 未填而阻塞本功能。若团队后续批准了与之冲突的原则（例如"前端不得新增独立组件"会挑战新 tab 组件），届时再 revisit。

## Project Structure

### Documentation (this feature)

```text
specs/005-related-entities-tab/
├── plan.md              # 本文件
├── research.md          # Phase 0 — R1..R7 设计决策
├── data-model.md        # Phase 1 — 请求/响应结构、store 新增字段、ErDiagramDotBuilder 新增方法
├── quickstart.md        # Phase 1 — 可运行的端到端验证场景
├── contracts/
│   ├── api.md           # Phase 1 — /er-diagram-subgraph 后端契约
│   └── ui.md            # Phase 1 — 前端 tab/手势/状态 UI 契约
└── tasks.md             # Phase 2 (/speckit-tasks — 本命令不创建)
```

### Source Code (repository root)

```text
src/nexusx/voyager/
├── er_diagram_dot.py        # [改] ErDiagramDotBuilder 加 render_dot_for_neighborhood() 类方法/备选构造路径
├── create_voyager.py        # [改] 加 POST /er-diagram-subgraph 端点 + ErDiagramSubgraphPayload 模型
├── voyager_context.py       # [改] （若需要）子图响应组装辅助
└── web/
    ├── component/
    │   ├── schema-code-display.js   # [改] 新增第三个 q-tab "Related Entities"，挂载子组件；保持 resetState 不重置 tab
    │   └── related-entities-display.js  # [新] 只读子图组件（d3-graphviz 渲染 + 加载/错误/空态 + pan/zoom）
    ├── graph-ui.js          # [改] 单击回调（侧边栏打开时触发 onSchemaClick）+ 空白点击关闭侧边栏（区分手势）
    ├── vue-main.js          # [改] 注册 RelatedEntitiesDisplay 组件；onSchemaClick 路径不变
    ├── store.js             # [改] 加 relatedEntities 子状态（loading/error/dot/selectedSchema）+ fetch action
    └── index.html           # [改] 在 schema-code-display 模板里加第三个 q-tab panels 区块

tests/
└── test_voyager_subgraph.py  # [新] ErDiagramDotBuilder.render_dot_for_neighborhood + /er-diagram-subgraph 端点测试
```

**Structure Decision**: 单一项目布局（沿用 `src/nexusx/`），无新增顶层目录。本功能是对现有 `voyager/` 子包的**纯追加式扩展**：后端复用 `ErDiagramDotBuilder`，前端复用 d3-graphviz 与现有 store/schema-code-display 模式，新增一个独立的前端组件文件 `related-entities-display.js` 以隔离子图渲染逻辑。

## Complexity Tracking

> 无 Constitution Check 违规，无需填表。
