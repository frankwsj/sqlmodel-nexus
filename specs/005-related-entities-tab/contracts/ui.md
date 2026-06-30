# UI Contract: Related Entities Tab + 侧边栏跟随选择

**Date**: 2026-06-30
**Spec**: [spec.md](../spec.md) | **Data Model**: [data-model.md](../data-model.md) | **Research**: [research.md](../research.md)

定义前端交互契约：新 tab 的视觉结构、所有手势的触发条件、以及四种视觉状态。后端契约见 [api.md](./api.md)。

---

## 1. Tab 结构（FR-001）

侧边栏组件 `schema-code-display`（`src/nexusx/voyager/web/component/schema-code-display.js`）的 `q-tabs` 区块当前有：

```
[ Fields ]  [ Source Code ]
```

本功能追加第三个 tab：

```
[ Fields ]  [ Source Code ]  [ Related Entities ]
```

- tab name: `"related"`；label: `"Related Entities"`。
- 三个 tab 的激活态由现有 `tab` ref（`schema-code-display.js:25`）管理，**不引入新的 tab 状态机**。
- **Tab 跨实体保留**（FR-012）：`resetState()`（`schema-code-display.js:48`）必须保持 `tab.value = "fields"` **被注释**的状态。切换实体时不重置 tab —— 此为现有不变量，本功能仅在测试中固化它。

## 2. 手势契约（FR-011 / FR-013）

### 2.1 单击实体（画布上）

| 侧边栏状态 | 行为 |
|-----------|------|
| **关闭** | 仅高亮一层邻居（现状，不变）；**不**触发 `onSchemaClick`，**不**打开侧边栏。 |
| **已打开** | 高亮一层邻居（现状）**且**触发 `onSchemaClick`，把 `schemaDetail.schemaCodeName` 切到被点实体；若当前 tab = Related Entities，自动 `fetchRelatedEntities`。 |

实现：在 `graph-ui.js` 的 `nodes.on("click.graphui", ...)` 处理器（`graph-ui.js:377`）末尾，读 `self.sidebarOpen`（新增布尔，从 store 同步），为 true 时额外 `self._triggerCallback("onSchemaClick", name)`。

### 2.2 双击实体（画布上）

| 侧边栏状态 | 行为 |
|-----------|------|
| **关闭** | 打开侧边栏，焦点为被双击的实体（现状，不变）。 |
| **已打开** | 等同于"单击该实体"（幂等）—— 触发 `onSchemaClick` 切焦点。 |

实现：现有 `nodes.on("dblclick.graphui", ...)`（`graph-ui.js:317`）不变。

### 2.3 空白处点击 vs 拖拽（FR-013）

| 手势 | 行为 |
|------|------|
| **纯点击**（mousedown→mouseup 位移 < 5px） | 关闭侧边栏（清空 `schemaCodeName` + `clearRelatedEntities()`）。 |
| **拖拽**（位移 ≥ 5px，用于平移/框选） | 侧边栏不变。 |
| 点击落在 node / edge / cluster 上 | 由 2.1 / 2.2 处理，不关闭侧边栏。 |

实现：在 `graph-ui.js` 的 document-level `click.graphui` 处理器（`graph-ui.js:388`）中，当 click target 不属于任何 node/edge/cluster 时，触发新增的 `onCanvasBackgroundClick` 回调；手势判定（click vs drag）复用画布现有的 mousedown/mouseup 位移阈值（详见 [research.md](../research.md) R6）。

## 3. 状态契约

子图区域（Related Entities tab 的内容）有四种互斥状态，视觉必须可区分：

| 状态 | 触发 | 视觉 |
|------|------|------|
| **加载中** | `fetchRelatedEntities` 进行中 | 顶部 `q-linear-progress`（沿用 `schema-code-display.js` 现有样式）；若已有旧 DOT，保留旧图直到新 DOT 返回（避免闪烁）；首次进入（无旧 DOT）显示居中 spinner。 |
| **正常** | 最近一次 fetch 成功 | 用 d3-graphviz 渲染返回的 DOT；启用 pan/zoom（FR-016）；不绑定任何 click/dblclick 回调到节点/边（FR-007）。 |
| **空（孤立实体）** | 最近一次成功响应 `dot` 仅含 `schema_name` 一个节点 | 渲染 `X` 自身孤立节点 + 叠加居中提示文案"该实体没有直接关联实体"（FR-005 / Clarifications Q2）。 |
| **错误** | HTTP 非 2xx / 网络异常 / `dot` 为空但非孤立场景 | 红色等宽错误文案（沿用 `schema-code-display.js` 的 `error` 渲染）。 |

## 4. 子图组件契约（FR-002 / FR-007 / FR-014 / FR-016）

新增组件 `src/nexusx/voyager/web/component/related-entities-display.js`：

- **Props**: `schemaName: string`、`config: { showModule, showMethods, edgeMinlen, showFields }`、`visible: boolean`。
- **渲染载体**: 一个独立的 d3-graphviz 实例（不复用主图 `GraphUI`）。
- **只读语义**: 不绑定节点/边的 click/dblclick；保留 d3-graphviz 内置 zoom/pan（FR-016）。
- **配置跟随**: `config` 任一字段变化 → 触发 `fetchRelatedEntities(schemaName)`（由 store action 处理，组件只负责把 prop 变化冒泡给 store）。
- **选择跟随**: `schemaName` 变化 → 触发 `fetchRelatedEntities(schemaName)`。
- **可见性**: `visible === false`（tab 未激活）时不发起 fetch；可见时若 `selectedSchema !== schemaName` 则发起 fetch。

## 5. 非目标（明确不在本功能范围）

- **不**在子图内提供实体选中 / 跳转 / 双击查看源码（FR-007）。
- **不**在子图区域显示任何配置控件（show_module / show_methods / edge_minlen 仅由主面板控制，FR-015）。
- **不**为子图引入独立的 filter / search / 模式切换。
- **不**修改 Fields / Source Code 两个现有 tab 的任何行为。
