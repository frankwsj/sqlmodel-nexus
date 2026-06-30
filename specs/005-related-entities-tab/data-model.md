# Data Model: Voyager ER 图 —— 关联实体侧边栏 Tab

**Date**: 2026-06-30
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md)

本功能**不引入任何持久化数据**。本文档描述：

1. 新增的**后端请求/响应模型**（pydantic）。
2. `ErDiagramDotBuilder` 上的**新增实例方法**（邻域过滤）。
3. 前端 `store` 的**新增内存字段**。

所有数据均为运行时内存态，与现有 voyager 一致。

---

## 后端请求模型（新增）

```python
# src/nexusx/voyager/create_voyager.py

class ErDiagramSubgraphPayload(PydanticModel):
    schema_name: str            # 所选实体的 full qualified id（module.Class）
    show_fields: str = "object"  # 与 ErDiagramPayload 同义
    show_module: bool = True
    edge_minlen: int = 3
    show_methods: bool = True
```

字段语义与现有 `ErDiagramPayload`（`create_voyager.py:64`）完全一致，额外多一个必填的 `schema_name`。`edge_minlen` 在后端同样被 clamp 到 `[3, 10]`（沿用 `voyager_context.py:166` 的 `max(3, min(10, ...))`）。

## 后端响应模型（无变化）

响应结构与现有 `GET /er-diagram` 完全一致（`voyager_context.py:161-206` 返回的 dict）：

```python
{
    "dot": str,                  # graphviz DOT 字符串（仅含邻域）
    "links": list[dict],         # 邻域内的边元数据
    "schemas": list[dict],       # 邻域内的节点元数据（含 fields）
}
```

不为子图引入新的响应字段，保持前端渲染管线与主图同构（前端用同一套 `{dot, links, schemas}` 消费逻辑）。

---

## `ErDiagramDotBuilder` 新增方法

**不改动** `__init__` / `analysis()` / `render_dot()` 的现有行为（spec 假设：现有 ER 渲染不变）。新增一个**邻域过滤**实例方法：

```python
# src/nexusx/voyager/er_diagram_dot.py — ErDiagramDotBuilder

def filter_to_neighborhood(self, schema_name: str) -> None:
    """在 analysis() 之后调用：把 nodes / node_set / links / link_set 收窄到
    schema_name 自身 + 其直接邻居 + 它们之间的边。

    - schema_name 不在 node_set 中 → 静默 no-op（前端会显示错误态/空态文案）。
    - 直接邻居定义：在 links 中出现、与 schema_name 同在 source 或 target 端的对端实体。
    - 自引用（X→X）保留为自环；循环（A↔B）保留为两条独立边。
    """
```

**调用顺序**（在 `voyager_context.py` 的新方法 `get_er_diagram_subgraph` 中）：

```python
builder = ErDiagramDotBuilder(self.er_manager, show_fields=..., show_module=..., ...)
builder.analysis()
builder.filter_to_neighborhood(schema_name)   # ← 新增一步
dot = builder.render_dot()
# links_meta / schemas_meta 从 builder.links / builder.node_set 提取（与现有路径同）
```

**邻域计算的权威性**：邻域来自 `ErManager.get_all_relationships()`（即主图同源），而非前端高亮所用的"当前已加载图的边"。在主图未应用过滤时，两者结果相同；应用过滤时，子图仍展示**注册表中权威的**直接关联（这是子图作为"聚焦视图"的预期行为，详见 [research.md](./research.md) R1）。

---

## 前端 store 新增字段

在 `src/nexusx/voyager/web/store.js` 的 `state` 中新增 `relatedEntities` 子状态：

```javascript
// store.js — state.relatedEntities（新增）
relatedEntities: {
    loading: false,
    error: null,           // string | null
    dot: "",               // 最近一次成功渲染的 DOT（用于切换时减少闪烁）
    links: [],
    schemas: [],
    selectedSchema: "",    // 当前子图对应的 schema_name（与 schemaDetail.schemaCodeName 同步）
}
```

**新增 action**（store method）：

```javascript
fetchRelatedEntities(schemaName) {
    // 用 buildErDiagramSubgraphPayload(schemaName) 组装 payload（复用 store.filter 的当前值）
    // POST /er-diagram-subgraph
    // 成功：写入 dot/links/schemas/selectedSchema，清 error
    // 失败：写 error，保留旧 dot
    // 期间：loading = true
}

clearRelatedEntities() {
    // 切换主图、关闭侧边栏、或离开 er-diagram 模式时调用
    // 清空 dot/links/schemas/selectedSchema，loading=false，error=null
}
```

**复用现有 filter 状态**：`buildErDiagramSubgraphPayload(schemaName)` 直接读 `state.filter.showModule / showMethods / edgeMinlen / showFields`，保证子图请求与主图请求的配置同源（spec FR-015）。**不为子图引入独立的 filter 字段。**

---

## 数据生命周期

| 触发事件 | store 动作 | 后端调用 |
|---------|-----------|---------|
| 用户双击实体 `X`（侧边栏关闭→打开） | `schemaDetail.schemaCodeName = X`；若当前 tab 是 Related Entities → `fetchRelatedEntities(X)` | `POST /er-diagram-subgraph` |
| 侧边栏已打开，用户单击实体 `Y`（FR-011） | `schemaDetail.schemaCodeName = Y`；若当前 tab 是 Related Entities → `fetchRelatedEntities(Y)` | `POST /er-diagram-subgraph` |
| 用户切换到 Related Entities tab（此前为 Fields/Source） | 触发 `fetchRelatedEntities(currentSchema)`（若尚未加载） | `POST /er-diagram-subgraph` |
| 主图配置变化（show_module / show_methods / edge_minlen）（FR-015） | 主图 refetch；若侧边栏开 + 当前 tab 是 Related Entities → `fetchRelatedEntities(currentSchema)` | 主图 `POST /er-diagram` + 子图 `POST /er-diagram-subgraph` |
| 用户在空白处纯点击（FR-013） | `schemaDetail.schemaCodeName = ""`；`clearRelatedEntities()` | 无 |
| 切换主图模式（离开 er-diagram） | `clearRelatedEntities()` | 无 |

Tab 保留（FR-012）由 `schema-code-display.js` 的 `resetState()` 中**已注释的** `tab.value = "fields"` 保证 —— 不引入新字段，不写新逻辑，仅在测试中固化该不变量。
