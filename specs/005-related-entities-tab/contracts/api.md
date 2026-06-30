# API Contract: `/er-diagram-subgraph`

**Date**: 2026-06-30
**Spec**: [spec.md](../spec.md) | **Data Model**: [data-model.md](../data-model.md) | **Research**: [research.md](../research.md)

新增的后端 HTTP 端点，为 Voyager ER 图侧边栏的 "Related Entities" tab 提供只读子图数据。复用现有 `ErDiagramDotBuilder` 的全部渲染逻辑，仅追加一步邻域过滤（详见 [data-model.md](../data-model.md)）。

---

## 端点

```
POST /er-diagram-subgraph
Content-Type: application/json
```

挂载于现有 voyager `APIRouter`（`src/nexusx/voyager/create_voyager.py`），与 `/er-diagram` 同级。**仅当 `ErManager` 已配置时可用**；未配置时返回与 `/er-diagram` 同样的空响应（`{"dot": "", "links": [], "schemas": []}`）。

## 请求

```json
{
  "schema_name": "string",     // 必填，所选实体的 full qualified id（module.Class）
  "show_fields": "object",      // 可选，默认 "object"；与 ErDiagramPayload 同义
  "show_module": true,          // 可选，默认 true
  "edge_minlen": 3,             // 可选，默认 3；后端 clamp 到 [3, 10]
  "show_methods": true          // 可选，默认 true
}
```

字段语义与现有 `ErDiagramPayload`（`create_voyager.py:64-68`）**完全一致**，额外多一个必填的 `schema_name`。`schema_name` 必须是 `ErManager` 注册表内已知的实体 full qualified 名；未知时返回 `dot=""` + 空 links/schemas（前端据此显示错误态/空态文案）。

## 响应

```json
{
  "dot": "digraph { ... }",     // graphviz DOT 字符串，仅含 schema_name + 直接邻居 + 边
  "links": [
    {
      "source_origin": "module.ClassA",
      "target_origin": "module.ClassB",
      "label": "string | null",
      "loader_fullname": "string | null"
    }
  ],
  "schemas": [
    {
      "id": "module.ClassA",
      "name": "ClassA",
      "module": "module",
      "fields": [
        { "name": "id", "type_name": "int", "from_base": false, "is_object": false, "is_exclude": false, "desc": "string | null" }
      ]
    }
  ]
}
```

响应结构与现有 `GET /er-diagram`（`voyager_context.py:161-206`）**完全相同**，保证前端用同一套消费逻辑。`links` / `schemas` 仅包含邻域内的项。

## 邻域语义

- **直接关联**：在 `ErManager.get_all_relationships()` 中，与 `schema_name` 同在 source 或 target 端的对端实体。
- 子图节点集合 = `{schema_name} ∪ {所有直接邻居}`。
- 子图边集合 = 所有两端都在节点集合内的关系。
- **自引用**（`schema_name` → `schema_name`）保留为自环。
- **循环**（`A` ↔ `B`，其中之一为 `schema_name`）保留为两条独立边（spec FR-010）。
- **孤立实体**（无任何关系）：节点集合 = `{schema_name}`，边集合 = `{}`。前端在该 DOT 之上叠加"该实体没有直接关联实体"提示文案（spec FR-005 / Clarifications Q2）。

## 错误处理

- `ErManager` 未配置 → 返回 `{"dot": "", "links": [], "schemas": []}`（200，与 `/er-diagram` 一致）。
- `schema_name` 未知 / 空字符串 → 返回 `{"dot": "", "links": [], "schemas": []}`（200）。前端据空 `dot` 显示错误态文案。
- 请求体不合法（pydantic 校验失败）→ FastAPI 默认 422。
- 服务端内部异常 → 沿用现有 voyager 的异常处理路径（500）。

**不引入新的错误码**；所有失败都被前端用"空 `dot` + 错误态文案"吸收，与 spec FR-006（明确、可读的错误状态）一致。

## 配置复用保证

`show_module` / `show_methods` / `edge_minlen` / `show_fields` 原样传入 `ErDiagramDotBuilder` 的构造函数（与 `/er-diagram` 同一行代码路径），从而：

- 主图与子图**共享同一份渲染规则**（spec FR-015）。
- 子图**不维护独立的配置存储**（spec FR-015）；配置的唯一来源是请求 payload，而 payload 由前端从同一份 `store.filter` 组装。

## 非目标

- **不**支持多跳邻域（spec 假设：v1 仅一层）。
- **不**返回 SVG / 渲染后的位图 —— 返回 DOT，前端用 d3-graphviz 渲染（与主图一致）。
- **不**接受过滤参数（如搜索关键字）—— 子图始终展示 `schema_name` 在注册表中的**全部**直接关联，与主图当前是否被过滤无关。
