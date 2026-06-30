# Quickstart: Voyager ER 图 —— 关联实体侧边栏 Tab

**Date**: 2026-06-30
**Spec**: [spec.md](./spec.md) | **Contracts**: [contracts/api.md](./contracts/api.md) · [contracts/ui.md](./contracts/ui.md) | **Data Model**: [data-model.md](./data-model.md)

可运行的端到端验证场景。每个场景映射到 spec 的验收场景 / 功能需求，用于证明本功能 works as designed。**不含完整实现代码**；实现细节归属 `tasks.md`（Phase 2）。

---

## 前置条件

- Python 3.10+，repo 在 `PYTHONPATH`（或 `uv sync` 后用 `uv run`）
- 浏览器（Chrome / Firefox / Safari 任一）
- `demo/enterprise_voyager` 可运行（38 个实体，关系丰富，是 spec 点名的主力验证场景）

---

## 场景 A —— 后端：邻域过滤与端点契约（自动化）

**目标**：证明 `ErDiagramDotBuilder.filter_to_neighborhood` 与 `POST /er-diagram-subgraph` 行为正确。映射到 spec FR-002 / FR-005 / FR-010 / FR-015，以及 [contracts/api.md](./contracts/api.md)。

**位置**：`tests/test_voyager_subgraph.py`（新建）。

**场景 A1 —— 邻域精确性（FR-002）**：

```python
def test_subgraph_contains_only_neighborhood(er_manager_with_demo_entities):
    builder = ErDiagramDotBuilder(er_manager_with_demo_entities, show_module=True, show_methods=True, edge_minlen=3)
    builder.analysis()
    builder.filter_to_neighborhood("demo.enterprise_voyager.models.Organization")
    # Organization 的直接邻居：Workspace, Department, Office, Vendor
    node_ids = {n.id for n in builder.node_set.values()}
    assert node_ids == {
        "demo.enterprise_voyager.models.Organization",
        "demo.enterprise_voyager.models.Workspace",
        "demo.enterprise_voyager.models.Department",
        "demo.enterprise_voyager.models.Office",
        "demo.enterprise_voyager.models.Vendor",
    }
    # 每条边的两端都必须在 node_ids 内
    for link in builder.links:
        assert link.source_origin in node_ids and link.target_origin in node_ids
```

**场景 A2 —— 孤立实体（FR-005）**：选一个无关系的实体（或在测试 fixture 中临时构造一个），过滤后 `node_set` 仅含自身，`links` 为空。

**场景 A3 —— 自引用 / 平行边（FR-010）**：在 fixture 中构造一个自引用实体与一对多关系实体，验证 `filter_to_neighborhood` 不合并平行边、不丢失自环。

**场景 A4 —— 配置透传（FR-015）**：用同一 `schema_name` 两次调用 `get_er_diagram_subgraph`，分别传 `show_methods=True` / `False`，验证返回的 `dot` 字符串不同（证明配置真正影响渲染）。

**场景 A5 —— 端点契约（[contracts/api.md](./contracts/api.md)）**：用 FastAPI `TestClient` 调 `POST /er-diagram-subgraph`，验证响应结构为 `{dot, links, schemas}`、`edge_minlen` 被 clamp 到 `[3,10]`、未知 `schema_name` 返回空 `dot`。

---

## 场景 B —— 前端 + 后端：端到端手动验证（demo）

**目标**：在真实浏览器里证明所有用户故事。映射到 spec Story 1（场景 1–6）+ Story 2 + 边界情况。

**启动**：

```bash
uv run uvicorn demo.enterprise_voyager.voyager_demo:app --port 8010
# 浏览器打开 http://localhost:8010/voyager
```

**B1 —— 子图渲染 + 邻域精确性（Story 1 场景 1、2）**：
1. 切到 ER Diagram 模式。
2. 双击 `Organization` 实体 → 侧边栏打开。
3. 切到 "Related Entities" tab。
4. **预期**：子图渲染 `Organization` + 其 4 个直接邻居（Workspace / Department / Office / Vendor）+ 5 条边；不渲染任何其他实体。每条边带方向与连接字段，视觉与主图同类边一致。

**B2 —— 孤立实体提示（Story 1 场景 3 / FR-005）**：
1. 找一个无关系的实体（或在 demo 中临时加一个孤立实体）。
2. 双击它 → Related Entities tab。
3. **预期**：子图只渲染该实体自身一个孤立节点 + 居中提示"该实体没有直接关联实体"。

**B3 —— 配置跟随（Story 1 场景 6 / FR-015）**：
1. 保持 B1 状态（Organization 子图可见）。
2. 在主面板切换 `Show Methods` 关闭 → 重新打开。
3. **预期**：子图随主图配置变化重新渲染；切换前后子图节点 label 中 query/mutation 方法行有无变化。子图区域内**不出现**任何独立配置控件。

4. 切换 `Edge Length` Small → Middle → Large。
5. **预期**：子图边长度随之变化。

**B4 —— 侧边栏跟随单击（Story 1 场景 5 / FR-011）**：
1. 保持侧边栏打开（在任意 tab）。
2. 在画布上**单击** `Workspace` 实体（不是双击）。
3. **预期**：侧边栏内容立即更新为 `Workspace`（Fields / Source Code / Related Entities 都反映 `Workspace`）；同时画布上 `Workspace` 的邻居高亮保留。

**B5 —— Tab 跨实体保留（FR-012）**：
1. 当前在 Related Entities tab，子图显示 `Workspace`。
2. 单击 `Department` 实体。
3. **预期**：侧边栏仍停留在 Related Entities tab（不切回 Fields）；子图刷新为 `Department` 的邻域。

**B6 —— 空白点击关闭、拖拽不关闭（FR-013）**：
1. 侧边栏打开状态。
2. 在画布**空白处**用鼠标"按下→松开（无明显移动）"。
3. **预期**：侧边栏关闭。
4. 重新打开侧边栏。在画布空白处"按下→拖动一段距离→松开"（平移视图）。
5. **预期**：侧边栏保持打开，画布平移。

**B7 —— 关系类型识别（Story 2 / FR-009）**：
1. 选一个同时拥有入向引用、出向引用、共享基类关系的实体。
2. 打开其 Related Entities tab。
3. **预期**：子图中的边通过一致且可区分的视觉标记传达方向与类型，与主图同类边语义一致。

---

## 场景 C —— 回归（保证不破坏现有行为）

**C1 —— 主图渲染不变**：`tests/` 现有 voyager / ER 图相关测试全部通过（spec 假设章节）。

**C2 —— 双击打开侧边栏不变**：侧边栏关闭时，双击实体仍然打开侧边栏（B1 步骤 2 验证）。

**C3 —— 单击只高亮（侧边栏关闭时）不变**：侧边栏关闭时，单击实体只高亮一层邻居、不打开侧边栏（FR-011 表格第一行）。

**C4 —— Fields / Source Code tab 不变**：两个现有 tab 的行为、样式、数据源完全不受本功能影响。

---

## 完成判定

本功能视为"通过 quickstart 验证"当且仅当：

- 场景 A1–A5 全部测试通过（自动化）。
- 场景 B1–B7 全部手动验证通过（结果与"预期"一致）。
- 场景 C1–C4 无回归。
