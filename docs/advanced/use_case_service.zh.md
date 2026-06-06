# UseCase 服务

将业务逻辑定义一次为服务类——同时服务于 MCP（AI 代理）和 FastAPI（REST API），无需重复。

## 设计理念

```
UseCaseService 子类 ──┬── MCP server（AI 代理，四层渐进式发现）
                      └── FastAPI routes（REST API，OpenAPI 文档）
```

一个服务类。两种呈现模式。零重复。

## 定义 UseCaseService

继承 `UseCaseService`，声明 `async classmethod` 方法。元类自动发现公共方法：

```python
from nexusx.use_case import UseCaseService

class SprintService(UseCaseService):
    """Sprint 管理服务。"""

    @classmethod
    async def list_sprints(cls) -> list[SprintSummary]:
        """获取所有 sprint 及其任务数。"""
        stmt = build_dto_select(SprintSummary)
        async with async_session() as session:
            rows = (await session.exec(stmt)).all()
        dtos = [SprintSummary(**dict(row._mapping)) for row in rows]
        return await Resolver().resolve(dtos)

    @classmethod
    async def get_sprint(cls, sprint_id: int) -> SprintSummary | None:
        """按 ID 获取 sprint。"""
        stmt = build_dto_select(SprintSummary, where=Sprint.id == sprint_id)
        async with async_session() as session:
            rows = (await session.exec(stmt)).all()
        if not rows:
            return None
        dto = SprintSummary(**dict(rows[0]._mapping))
        return await Resolver().resolve(dto)
```

!!! tip
    每个方法的 docstring 会成为 MCP 工具的描述——写清楚它们，让 AI 代理知道何时该用哪个方法。

## 暴露到 MCP

四层渐进式发现：应用发现 → 服务列表 → 方法详情 → 执行。

```python
from nexusx.use_case import UseCaseAppConfig, create_use_case_mcp_server

mcp = create_use_case_mcp_server(
    apps=[
        UseCaseAppConfig(
            name="project",
            services=[SprintService, TaskService],
            description="Project management",
        ),
    ],
    name="Project UseCase API",
)
mcp.run()  # stdio 模式
```

### MCP 工具

| 工具 | 用途 |
|------|------|
| `list_apps()` | 发现可用应用 |
| `list_services(app_name)` | 列出应用中的服务和方法数量 |
| `describe_service(app_name, service_name)` | 方法签名（SDL 格式）+ DTO 类型定义 |
| `call_use_case(app_name, service_name, method_name, params)` | 执行方法 |

### describe_service 输出

```json
{
  "name": "SprintService",
  "methods": [
    {"name": "list_sprints", "signature_sdl": "list_sprints(): [SprintSummary!]!"},
    {"name": "get_sprint", "signature_sdl": "get_sprint(sprint_id: Int!): SprintSummary"}
  ],
  "types": "type SprintSummary {\n  id: Int\n  name: String!\n  tasks: [TaskSummary!]!\n}"
```

四层设计让 AI 代理渐进式地探索你的 API——先看全貌，再根据需要深入具体的服务和方法。

## 回顾

- `UseCaseService` 子类将业务逻辑定义为 `async classmethod` 方法
- 元类自动发现公共方法——以下划线 `_` 开头的私有方法会被排除
- `create_use_case_mcp_server` 创建四层渐进式发现的 MCP 服务
- 方法的 docstring 成为 AI 代理看到的 MCP 工具描述

## 下一步

- [UseCase + FastAPI](./use_case_fastapi.zh.md) — 同一服务类嵌入 FastAPI
- [MCP 服务](./mcp_service.zh.md) — 纯 MCP 集成（GraphQL 模式）
