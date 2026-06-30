# Research: Voyager ER 图 —— 关联实体侧边栏 Tab

**Date**: 2026-06-30
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

本文档记录 `/speckit-plan` Phase 0 阶段对 7 个设计问题的决策、理由与被否决的备选。所有决策直接映射到 spec 的功能需求（FR-001..FR-016）与 plan 的 Technical Context。

---

## R1: 子图数据来源 —— 后端接口 vs 客户端过滤

**Decision**: 新增后端接口 `POST /er-diagram-subgraph`，由 `ErDiagramDotBuilder` 复用现有渲染逻辑生成子图 DOT；前端用新的 d3-graphviz 实例渲染。

**Rationale**:
- 后端 `ErDiagramDotBuilder`（`src/nexusx/voyager/er_diagram_dot.py:77`）已经集中了全部 DOT 生成与样式逻辑：`show_fields` / `show_module` / `edge_minlen` / `show_methods` / `theme_color`。spec FR-015 要求"复用主图当前的渲染配置"，最直接的复用就是把同一套参数再喂给同一个 builder。
- 客户端目前持有 `{dot, links, schemas}` 三件套（`vue-main.js renderErDiagram()` 缓存），其中 `dot` 是**已渲染好的 DOT 字符串**，`links`/`schemas` 是结构化数据但**不含样式规则**（cluster 分组、field/method 渲染、edge_minlen 都在 builder 内部）。客户端自行重构 DOT 等于重写一遍 builder，违反 DRY，且与主图样式必然漂移。
- 邻域计算的权威来源是 `ErManager` 实体注册表（后端），它就是主图的数据源。从同一注册表计算邻域，能保证子图与主图对"直接关联"的语义**完全同源**（spec FR-002）。
- 服务端往返的成本可控：子图节点数 ≤ 主图（通常 ≤ 数十），DOT 生成 < 50 ms（见 plan Performance Goals），满足 spec SC-005"感知为即时"。

**Alternatives considered**:
- **客户端过滤 DOT 字符串**：解析主图 DOT、抽取子图、重新喂给 d3-graphviz。被否决：DOT 解析脆弱（graphviz 语法复杂），且无法应用配置变化（例如 toggling `show_methods` 需要重新生成节点 label，而不是简单过滤）。
- **客户端从 `links`/`schemas` 重构 DOT**：被否决：需要在 JS 里复刻 `ErDiagramDotBuilder` 的全部样式逻辑（cluster 折叠、字段表渲染、方法行、edge_minlen），维护负担高，且与后端样式极易漂移。
- **复用主图 d3-graphviz 实例做局部高亮隐藏**：被否决：spec 要求子图是侧边栏内的**独立聚焦视图**，不是主图上的视觉过滤；同屏两个图共享实例会互相污染布局状态。

---

## R2: 子图渲染载体 —— 新建 d3-graphviz 实例

**Decision**: 在新增组件 `related-entities-display.js` 内部，对子图容器选择器调用 `d3.select(sel).graphviz(...)`，创建一个**独立于主图**的 d3-graphviz 实例。

**Rationale**:
- d3-graphviz 的实例状态（缩放、平移、布局）是 per-element 的；独立实例保证主图与子图的视图状态互不干扰。
- 现有 `GraphUI`（`graph-ui.js`）是为带交互（点击、高亮、拖拽）的主图设计的；子图**只读**（spec FR-007/FR-016），不复用 `GraphUI` 的交互层，避免误启用选中/导航。
- 子图实例的生命周期跟随 tab 可见性：tab 隐藏时不需要销毁（保留 d3-graphviz 状态），但 fetch 仅在 tab 激活或所选实体变化时触发。

**Alternatives considered**:
- **复用 `GraphUI` 类 + 一个 "readonly" flag**：被否决：`GraphUI` 的交互绑定（`nodes.on("click.graphui")` 等）是构造时硬连线的，加 flag 会让该类承担两种角色，复杂度上升；新建轻量组件更清晰。
- **SVG 静态嵌入（不挂 d3-graphviz）**：被否决：会失去 pan/zoom（spec FR-016 允许的视图操作），且后端返回的是 DOT 而非 SVG。

---

## R3: 配置复用机制 —— 直通 `ErDiagramDotBuilder`

**Decision**: `/er-diagram-subgraph` 端点的请求 payload 字段与现有 `/er-diagram` **完全一致**（`show_fields` / `show_module` / `edge_minlen` / `show_methods` + 主题色），额外增加 `schema_name`。后端把这些参数原样传给一个新的构造路径 `ErDiagramDotBuilder.render_dot_for_neighborhood(schema_name, ...)`，该路径在生成 nodes/links 时**先过滤到邻域**，再走原有的 `DiagramRenderer.render_dot()`。

**Rationale**:
- 配置复用 = 字段透传 + 同一 builder。这样"主图配置变化 → 子图自动跟随"（spec FR-015 / Story 1 场景 6）等价于"前端用最新 store.filter 重新调用 `/er-diagram-subgraph`"，无需额外的配置同步机制。
- 前端在 `store.js` 已有的 `buildErDiagramPayload()`（`store.js:576`）基础上加一个 `buildErDiagramSubgraphPayload(schema_name)`，复用同一份 filter 状态，保证两个请求的配置始终同源。

**Alternatives considered**:
- **子图维护自己的配置存储，初次从主图快照**：被否决：违反 spec FR-015"不维护子图自己的配置存储"，且会随主图配置变化而陈旧。
- **后端缓存上次主图配置，子图请求只发 schema_name**：被否决：后端无状态原则（现有 `/er-diagram` 也是无状态），引入会话状态会破坏现有架构。

---

## R4: 只读语义与 pan/zoom

**Decision**: 子图组件**不绑定**任何 `click`/`dblclick` 回调到节点或边；d3-graphviz 实例保留其内置的 zoom/pan 行为（spec FR-016：允许视图操作，禁止选中/导航）。

**Rationale**:
- d3-graphviz 默认支持鼠标滚轮缩放与拖拽平移；这些是视图操作，不改变 `store.state.schemaDetail.schemaCodeName`，因此与"只读"不冲突。
- 不绑定 click 回调 = 子图内点击实体**不会**触发 `onSchemaClick`，从而不会把主图选区切走（spec FR-007）。

**Alternatives considered**:
- **完全禁用子图交互（含 pan/zoom）**：被否决：当邻居数较多（如 30+）时，用户需要缩放/平移才能看清边与标签（spec 边界情况："直接邻居数量非常多"）。

---

## R5: 侧边栏跟随选择（FR-011 / FR-012 / FR-013）—— 纯前端改动

**Decision**: 三条需求各自的前端落点如下：

- **FR-011（单击触发更新）**：在 `graph-ui.js` 的 `nodes.on("click.graphui", ...)` 处理器（`graph-ui.js:377`）末尾，**当侧边栏处于打开状态时**，额外调用 `self._triggerCallback("onSchemaClick", name)`。判断"打开状态"由一个新增的 `self.sidebarOpen` 布尔（从 store 同步）承担。双击处理器（`graph-ui.js:317`）不变 —— 它已经在所有情况触发 `onSchemaClick`，满足"双击幂等"。
- **FR-012（tab 保留）**：**零代码改动**。`schema-code-display.js` 的 `resetState()`（`schema-code-display.js:48`）已经把 `tab.value = "fields"` 注释掉，因此 schemaName 变化时 tab 自然保留。只需加一个回归测试/手验脚本，确保未来不会误恢复该行。
- **FR-013（空白点击关闭，拖拽不关闭）**：在 `graph-ui.js` 的 document-level `click.graphui` 处理器（`graph-ui.js:388`）中，当 click target 不属于任何 node/edge/cluster（即背景）时，调用一个新增的 `onCanvasBackgroundClick` 回调；前端 store 收到后判断"是否为纯点击"（见 R6），若是则清空 `schemaCodeName`。

**Rationale**:
- 现有 dblclick 路径已经做对了一切（高亮 + 触发回调），单击路径只差"触发回调"这一步，最小改动就是补上。
- tab 保留是现有代码的既成事实，写进 plan 是为了防止回归，而不是要新做。
- 空白点击关闭是新的前端行为，但手势判定可以复用现有逻辑（R6）。

**Alternatives considered**:
- **把 `onSchemaClick` 合并到 `click` 处理器（无条件触发）**：被否决：侧边栏关闭时，单击就触发回调会改变现有"单击只高亮"的语义，破坏现有交互。
- **用一个新的 `onSchemaSelect` 轻量回调（不重新高亮）**：可行但非必要 —— 单击路径在触发回调前已经做完了高亮，复用 `onSchemaClick` 更简单。

---

## R6: 空白处 click vs drag 的判定

**Decision**: 在画布容器的 mousedown 上记录起始坐标与时间，在 mouseup 上计算位移；位移 < 阈值（例如 5px）且未发生拖拽事件，则认定为"纯点击"，触发关闭；否则视为拖拽（平移/框选），不触发关闭。**沿用画布现有的 mousedown/mouseup 位移判定**，不引入新的手势识别库。

**Rationale**:
- spec FR-013 明确要求"click 与 drag 的判定沿用画布现有的逻辑，不引入新的判定机制"。
- d3-graphviz 的平移本身就会产生 mousedown→mousemove→mouseup 序列；在 mouseup 上看位移是最简单可靠的判据。

**Alternatives considered**:
- **用 click 事件 + 检查 `event.detail`（点击次数）**：被否决：`detail` 区分的是单击/双击，不是点击/拖拽，不适用。
- **用 `pointermove` 事件计数**：可行但比位移阈值更复杂，且 d3-graphviz 内部已用 mouse 事件，混用 pointer 事件易冲突。

---

## R7: 加载 / 错误 / 空态

**Decision**:
- **加载态**：子图容器顶部显示 `q-linear-progress`（沿用 `schema-code-display.js` 现有样式）；旧 DOT 不清空，直到新 DOT 返回（避免闪烁）。若首次进入（无旧 DOT），显示居中 spinner。
- **错误态**（spec FR-006）：HTTP 非 2xx 或网络异常时，子图区域显示红色等宽错误文案（沿用 `schema-code-display.js` 的 `error` 渲染），与空态视觉区分。
- **空态**（spec FR-005）：所选实体无任何关联实体时，子图渲染 `X` 自身一个孤立节点 + 一句"该实体没有直接关联实体"提示文案（spec Story 1 场景 3 / Clarifications Q2）。这由后端返回的 DOT 仅含 `X` 一个节点来表达，前端叠加提示文案。

**Rationale**:
- 三种状态必须视觉可区分（加载中 / 出错 / 无关系），否则用户无法判断"为什么图是空的"。
- 空态选择"渲染 X 自身 + 文案"（而非纯空状态）来自用户在 Clarifications Q2 的明确选择。

**Alternatives considered**:
- **空态不渲染任何图，只显示文案**：被否决：这是 Clarifications Q2 的选项 A，用户选了 B（渲染 X + 文案）。

---

## 未决项（留待 Phase 2 tasks 拆分时定论）

以下三项是 `/speckit-clarify` 上一轮报告的 Outstanding 低影响项，给出 plan 阶段的默认决策，可在 tasks.md 细化时调整：

1. **自引用（X→X）/ 循环（A↔B）的渲染**：默认由 `ErDiagramDotBuilder` 的现有 DOT 生成自然表达（自引用 = 自环，循环 = 两条独立边），不做特殊处理。若 graphviz 对自环布局不佳， Phase 2 再加样式微调。
2. **schema 在 tab 打开期间被重新生成**：默认不热刷新；子图数据在下次"所选实体变化 / 侧边栏重开 / 主图配置变化触发 refetch"前保持陈旧。这与主图当前的缓存行为一致。
3. **加载态视觉骨架**：见 R7（顶部 `q-linear-progress` + 首次居中 spinner）。
