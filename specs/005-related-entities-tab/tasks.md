---

description: "Task list for 005-related-entities-tab feature implementation"
---

# Tasks: Voyager ER 图 —— 关联实体侧边栏 Tab

**Input**: Design documents from `/specs/005-related-entities-tab/`（[plan.md](./plan.md)、[spec.md](./spec.md)、[research.md](./research.md)、[data-model.md](./data-model.md)、[contracts/](./contracts/)、[quickstart.md](./quickstart.md)）

**Prerequisites**: plan.md（必填）、spec.md（必填，含用户故事与优先级）、research.md、data-model.md、contracts/api.md、contracts/ui.md

**Tests**: 本功能的 [quickstart.md](./quickstart.md) **场景 A（A1–A5）显式定义为 pytest 自动化测试**，因此 tasks 包含后端测试任务（TDD，先写测试使其失败）。前端无自动化测试基础设施（与现有 voyager 前端一致），按 [quickstart.md](./quickstart.md) 场景 B/C 做手动验证。

**Organization**: 按 spec 的用户故事分组 —— Phase 2 Foundational 承载跨 tab 的"侧边栏跟随选择"行为（FR-011/012/013，spec Story 1 场景 4–6 的前置）；Phase 3 = Story 1（P1，MVP）；Phase 4 = Story 2（P2）。

## Format: `[ID] [P?] [Story?] Description (file path)`

- **[P]**：可并行（不同文件、无依赖）
- **[US1]/[US2]**：归属的用户故事（来自 spec.md）
- 所有任务都标注精确文件路径

## Path Conventions

- 后端：`src/nexusx/voyager/`、测试 `tests/`
- 前端：`src/nexusx/voyager/web/`（含 `component/`）
- 单项目布局（沿用现有 repo 结构，详见 [plan.md](./plan.md) Project Structure）

---

## Phase 1: Setup（基线确认）

**Purpose**: 确认改动起点是绿的，避免后续混淆"本功能引入的回归"与"既有问题"。

- [x] T001 确认基线：运行 `uv run uvicorn demo.enterprise_voyager.voyager_demo:app --port 8010` 打开 `http://localhost:8010/voyager`，确认 ER Diagram 模式可加载；运行 `uv run pytest -q` 确认现有测试全绿（记录基线测试数，供 Phase 5 对比）

---

## Phase 2: Foundational —— 侧边栏跟随选择（FR-011 / FR-012 / FR-013）

**Purpose**: 跨 tab 的侧边栏响应性修复，是 spec Story 1 场景 4–6 的前置条件。**这些行为同时惠及 Fields / Source Code / Related Entities 三个 tab。**

**⚠️ 必须先于 Story 1 完成**：Story 1 的验收场景 5（单击触发侧边栏更新）依赖本阶段的 FR-011。

- [x] T002 在 `src/nexusx/voyager/web/graph-ui.js` 的 `GraphUI` 上新增 `sidebarOpen` 响应式标志，从 `store.state.schemaDetail.schemaCodeName` 同步（非空 = 打开）
- [x] T003 实现 FR-011：在 `src/nexusx/voyager/web/graph-ui.js` 的 `nodes.on("click.graphui", ...)` 处理器（约 `:377`）末尾，当 `self.sidebarOpen === true` 时额外调用 `self._triggerCallback("onSchemaClick", name)`（依赖 T002）
- [x] T004 实现 FR-013：在 `src/nexusx/voyager/web/graph-ui.js` 的 document-level `click.graphui` 处理器（约 `:388`）中，识别"背景点击"（target 不属于 node/edge/cluster）并触发新增的 `onCanvasBackgroundClick` 回调；前端 store 在收到回调时用现有 mousedown/mouseup 位移阈值（< 5px = 纯点击）判定手势，纯点击则清空 `schemaCodeName`（依赖 T002）
- [x] T005 [P] 实现/固化 FR-012：在 `src/nexusx/voyager/web/component/schema-code-display.js` 的 `resetState()`（约 `:48`）确认 `tab.value = "fields"` 保持注释状态，添加一行 protective comment 说明"切换实体时不得重置 tab（spec FR-012）"

**Checkpoint**: 侧边栏跟随单击、空白点击关闭、tab 跨实体保留 —— 三个行为均可手验（无需等 Story 1）。

---

## Phase 3: User Story 1 —— 关联实体只读子图（Priority: P1）🎯 MVP

**Goal**: 在双击侧边栏中新增 "Related Entities" tab，渲染只读的迷你 ER 子图（所选实体 + 直接邻居 + 边），复用主图配置并随其变化（spec FR-001..006、FR-014..016）。

**Independent Test**: [quickstart.md](./quickstart.md) 场景 B1（子图渲染 + 邻域精确性）+ B3（配置跟随）+ B4（侧边栏跟随单击）+ B5（tab 保留）—— 四个手动场景全过即视为 Story 1 独立可用。

### Tests for User Story 1（TDD，先写使其失败）

- [x] T006 [P] [US1] 编写后端测试（[quickstart.md](./quickstart.md) 场景 A1–A5）于 `tests/test_voyager_subgraph.py`：邻域精确性（A1）、孤立实体（A2）、自引用/平行边（A3）、配置透传（A4）、端点契约（A5）。**期望失败**（被测代码尚未实现）

### Backend Implementation for User Story 1

- [x] T007 [P] [US1] 实现 `ErDiagramDotBuilder.filter_to_neighborhood(schema_name: str) -> None` 于 `src/nexusx/voyager/er_diagram_dot.py`：在 `analysis()` 之后调用，把 `nodes` / `node_set` / `links` / `link_set` 收窄到 `schema_name` + 直接邻居 + 它们之间的边；未知 schema 静默 no-op；保留自引用与平行边
- [x] T008 [US1] 实现 `VoyagerContext.get_er_diagram_subgraph(payload: dict) -> dict` 于 `src/nexusx/voyager/voyager_context.py`：组装 `ErDiagramDotBuilder` → `analysis()` → `filter_to_neighborhood(payload["schema_name"])` → `render_dot()` + 提取 links/schemas meta；响应结构与现有 `get_er_diagram_data` 完全一致（依赖 T007）
- [x] T009 [US1] 在 `src/nexusx/voyager/create_voyager.py` 新增 `ErDiagramSubgraphPayload` pydantic 模型（字段见 [data-model.md](./data-model.md)）+ 注册 `@router.post("/er-diagram-subgraph")` 端点，调用 `ctx.get_er_diagram_subgraph(payload.model_dump())`（依赖 T008）

### Frontend Implementation for User Story 1

- [x] T010 [P] [US1] 在 `src/nexusx/voyager/web/store.js` 新增 `state.relatedEntities` 子状态（`loading` / `error` / `dot` / `links` / `schemas` / `selectedSchema`）+ `fetchRelatedEntities(schemaName)` action（POST `/er-diagram-subgraph`，payload 由新增的 `buildErDiagramSubgraphPayload(schemaName)` 从 `store.filter` 组装）+ `clearRelatedEntities()` action
- [x] T011 [P] [US1] 新建 `src/nexusx/voyager/web/component/related-entities-display.js`：`RelatedEntitiesDisplay` Vue 组件，props `{ schemaName, config, visible }`；用独立 d3-graphviz 实例渲染 DOT；实现四种状态（加载中 / 正常 / 空孤立节点 + 文案 / 错误）；**只读**（不绑定 click/dblclick）；保留 pan/zoom
- [x] T012 [P] [US1] 在 `src/nexusx/voyager/web/vue-main.js` 全局注册 `RelatedEntitiesDisplay` 组件（依赖 T011）
- [x] T013 [US1] 在 `src/nexusx/voyager/web/component/schema-code-display.js` 的模板 `q-tabs` 区块追加第三个 `<q-tab name="related" label="Related Entities" />` + 对应 `q-tab-panel`，挂载 `<related-entities-display>`（依赖 T011）
- [x] T014 [US1] 在 `src/nexusx/voyager/web/component/related-entities-display.js` 接线响应式：watch `schemaName` 变化 → 触发 `fetchRelatedEntities`；watch `config` 任一字段变化 → 触发 `fetchRelatedEntities`；tab 首次激活且 `selectedSchema !== schemaName` 时触发 fetch（依赖 T010、T011）

**Checkpoint**: Story 1 完整可用 —— 后端测试 A1–A5 全绿 + 前端 B1/B3/B4/B5 手验通过。

---

## Phase 4: User Story 2 —— 关系类型与方向的视觉识别（Priority: P2）

**Goal**: 子图中的边以一致、可区分的视觉传达关系类型/方向（入向、出向、双向、共享基类），且平行边不被合并（spec FR-009、FR-010）。

**Independent Test**: [quickstart.md](./quickstart.md) 场景 B7（关系类型识别手验）。

**说明**: 因子图复用 `ErDiagramDotBuilder` 的渲染逻辑，边的视觉语义天然与主图一致 —— Story 2 主要是**验证 + 固化断言**，几乎无新代码。

- [x] T015 [US2] 在 `tests/test_voyager_subgraph.py` 扩展测试：断言子图边方向/类型与主图同类边一致（FR-009），断言 `filter_to_neighborhood` 不合并平行边、不丢失自环（FR-010）（依赖 T007）
- [x] T016 [US2] 按 [quickstart.md](./quickstart.md) 场景 B7 手动验证：选一个同时有入向/出向/共享基类关系的实体，确认子图边视觉可区分

**Checkpoint**: Story 2 通过，Story 1 + Story 2 均独立可用。

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: 端到端验证、回归扫尾、交付前检查。

- [x] T017 [P] 执行 [quickstart.md](./quickstart.md) 场景 B（B1–B7）端到端手动验证，记录并修复发现的问题
- [x] T018 [P] 执行 [quickstart.md](./quickstart.md) 场景 C（C1–C4）回归验证：主图渲染不变、双击打开不变、Fields/Source Code tab 不变、单击只高亮（侧边栏关时）不变
- [x] T019 运行 `uv run pytest -q` + `uv run ruff check` 全绿（测试数 ≥ 基线 + 新增 A1–A5/FR-009/FR-010 测试）；最终代码 review

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1（Setup）**: 无依赖，立即开始。
- **Phase 2（Foundational）**: 依赖 Phase 1 完成。**阻塞 Story 1**（场景 5 依赖 FR-011）。
- **Phase 3（Story 1 / MVP）**: 依赖 Phase 2 完成。后端先于前端（前端依赖 `/er-diagram-subgraph` 契约稳定）。
- **Phase 4（Story 2）**: 依赖 Story 1 的 T007（`filter_to_neighborhood`）存在。
- **Phase 5（Polish）**: 依赖 Story 1 与 Story 2 均完成。

### User Story Dependencies

- **Story 1（P1）**：可在 Phase 2 完成后开始；不依赖 Story 2。
- **Story 2（P2）**：依赖 Story 1 的后端 `filter_to_neighborhood`（T007），但只是**测试/验证**层面，无新前端代码。

### Within Each User Story

- 测试先写（TDD，期望失败）→ 后端 model → 后端 service → 后端 endpoint → 前端 store → 前端组件 → 前端接线
- 后端先于前端（前端组件依赖后端契约）

### Task-level Dependencies

| Task | 依赖 |
|------|------|
| T003 | T002 |
| T004 | T002 |
| T008 | T007 |
| T009 | T008 |
| T012 | T011 |
| T013 | T011 |
| T014 | T010, T011 |
| T015 | T007 |

其余任务（T001、T005、T006、T007、T010、T011、T016、T017、T018、T019）可在所属阶段开始后立即开始（受阶段依赖约束）。

### Parallel Opportunities

- **Phase 2**：T005（schema-code-display.js）可与 T002–T004（graph-ui.js）并行。
- **Phase 3 后端**：T006（测试）、T007（builder 方法）可并行（不同文件）。
- **Phase 3 前端**：T010（store.js）、T011（新组件文件）可并行；T012（vue-main.js）、T013（schema-code-display.js）在 T011 完成后可并行。
- **Phase 4**：T015（测试扩展）与 T016（手验）可并行。
- **Phase 5**：T017、T018 可并行（不同验证目标）。

---

## Parallel Example: User Story 1

```bash
# 后端 leaf 任务（不同文件，可同时启动）：
Task: "T006 写后端测试于 tests/test_voyager_subgraph.py"
Task: "T007 实现 filter_to_neighborhood 于 src/nexusx/voyager/er_diagram_dot.py"

# 前端 scaffold（不同文件，可同时启动）：
Task: "T010 加 relatedEntities 状态于 src/nexusx/voyager/web/store.js"
Task: "T011 新建 src/nexusx/voyager/web/component/related-entities-display.js"

# 前端接线（T011 完成后，不同文件，可同时启动）：
Task: "T012 注册组件于 src/nexusx/voyager/web/vue-main.js"
Task: "T013 加 q-tab 于 src/nexusx/voyager/web/component/schema-code-display.js"
```

---

## Implementation Strategy

### MVP First（仅 Story 1）

1. **Phase 1**：基线确认（T001）。
2. **Phase 2**：侧边栏跟随选择（T002–T005）—— **CRITICAL，阻塞 Story 1 场景 5**。
3. **Phase 3**：Story 1 完整交付（T006–T014）。
4. **STOP & VALIDATE**：[quickstart.md](./quickstart.md) 场景 A（自动化）+ B1/B3/B4/B5（手验）全过。
5. 可交付/可演示：用户能在大型 schema（如 `demo/enterprise_voyager`）上，于侧边栏内看到任意实体的聚焦关联子图，并随主图配置/选择变化。

### Incremental Delivery

1. Phase 1 + 2 → 侧边栏响应性修复（惠及所有 tab）。
2. + Story 1 → 关联实体子图 MVP。
3. + Story 2 → 边类型/方向视觉识别固化（主要为测试）。
4. + Phase 5 → 端到端 + 回归扫尾。

### Suggested MVP Scope

**MVP = T001 → T014（Setup + Foundational + Story 1）**，共 14 个任务。Story 2（T015–T016）与 Polish（T017–T019）可在 MVP 验收后再做。

---

## Notes

- 所有后端改动是**追加式**：`ErDiagramDotBuilder` / `/er-diagram` 现有行为不变（spec 假设）。
- 前端不引入构建链：仍是全局脚本 + ES module + Vue 全局组件。
- `schema-code-display.js` 同时被 T005（Phase 2，加 protective comment）与 T013（Phase 3，加 q-tab）触碰 —— 两任务在不同 Phase，按顺序执行无冲突。
- `graph-ui.js` 被 T002/T003/T004 触碰 —— 同文件，按 ID 顺序执行。
- 每个任务或逻辑分组完成后 commit；在任一 Checkpoint 可停下来独立验证。
