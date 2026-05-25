# UseCase API 参考

UseCaseService、UseCaseAppConfig、create_use_case_mcp_server、create_use_case_voyager 的完整 API 参考。

## UseCaseService

业务服务基类。子类声明 `async classmethod` 方法，元类自动发现公共方法。

```python
from nexusx.use_case import UseCaseService
from nexusx import query, mutation

class SprintService(UseCaseService):
    """Sprint 管理服务。"""

    @query
    async def list_sprints(cls) -> list[SprintSummary]:
        ...

    @query
    async def get_sprint(cls, sprint_id: int) -> SprintSummary | None:
        ...

    @mutation
    async def create_sprint(cls, name: str) -> SprintSummary:
        ...
```

### 规则

- 方法必须使用 `@query` 或 `@mutation` 装饰器
- 方法必须是 `async`，第一个参数为 `cls`
- 方法名以 `_` 开头的不会被自动发现
- docstring 成为 MCP 工具的描述

### 类方法

| 方法 | 说明 |
|------|------|
| `get_tag_name()` | 返回类名作为标签（如 `"SprintService"`） |

## UseCaseAppConfig

应用配置类，将一组 UseCaseService 组织为一个应用。

```python
from nexusx.use_case import UseCaseAppConfig

config = UseCaseAppConfig(
    name="project",
    services=[SprintService, TaskService],
    description="Project management API",
)
```

### 参数

| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `name` | `str` | 是 | 应用名称 |
| `services` | `list[type[UseCaseService]]` | 是 | UseCaseService 子类列表 |
| `description` | `str \| None` | 否 | 应用描述 |
| `context_extractor` | `Callable \| None` | 否 | MCP 上下文提取函数 |

## create_use_case_mcp_server

创建 UseCase 服务的 MCP 服务端，支持多应用和四层渐进式发现。

```python
from nexusx.use_case import create_use_case_mcp_server, UseCaseAppConfig

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
```

### 参数

| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `apps` | `list[UseCaseAppConfig]` | 是 | 应用配置列表 |
| `name` | `str` | 否 | 服务名称 |

### 生成的 MCP 工具

| 工具 | 说明 |
|------|------|
| `list_apps()` | 列出所有可用应用 |
| `list_services(app_name)` | 列出应用中的服务和方法数量 |
| `describe_service(app_name, service_name)` | 返回 SDL 格式的方法签名和类型定义 |
| `call_use_case(app_name, service_name, method_name, params)` | 执行方法 |

## create_flat_mcp_server

创建扁平化 MCP 服务器，每个 UseCase 方法直接暴露为独立 tool — 无渐进披露。

```python
from nexusx.use_case import create_flat_mcp_server, UseCaseAppConfig

mcp = create_flat_mcp_server(
    apps=[
        UseCaseAppConfig(
            name="project",
            services=[SprintService, TaskService],
        ),
    ],
    name="Project API",
)
```

### 参数

| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `apps` | `list[UseCaseAppConfig]` | 是 | 应用配置列表 |
| `name` | `str` | 否 | 服务器名称 |

### 生成的 MCP 工具

每个 `@query`/`@mutation` 方法注册为独立 tool，命名为 `{ServiceName}_{method_name}`。方法参数从 Python 签名直接映射（排除 `cls` 和 `FromContext` 参数）。自动添加可选的 `selection` 参数用于字段投影。

| 示例工具 | 来源 |
|---------|------|
| `SprintService_list_sprints()` | `SprintService.list_sprints` |
| `TaskService_get_task(task_id)` | `TaskService.get_task` |
| `TaskService_delete_task(task_id)` | `TaskService.delete_task`（mutation） |

### 生成的 MCP 资源

每个 app 一个资源：`nexusx://{app_name}` — 包含所有 service 的方法签名、描述和 SDL 类型定义。

### 与 create_use_case_mcp_server 对比

| 特性 | 渐进披露（4 层） | 扁平化 |
|------|----------------|--------|
| 工具数量 | 4 个固定工具 | 每个方法一个 tool |
| 发现流程 | list_apps → list_services → describe_service → call | 直接调用 |
| 类型定义 | describe_service 返回值 | MCP resource |
| 适用场景 | 大型 API、多服务 | 小型 API、直接访问 |

## create_use_case_voyager

创建 Voyager 可视化 ASGI 子应用。

```python
from nexusx.voyager import create_use_case_voyager

voyager = create_use_case_voyager(
    apps=[
        UseCaseAppConfig(
            name="project",
            services=[SprintService, TaskService],
        ),
    ],
)
```

### REST 端点

| 端点 | 说明 |
|------|------|
| `/dot` | DOT 格式服务依赖图 |
| `/dot-search` | 可搜索的 DOT 图 |
| `/er-diagram` | Mermaid ER 图 |
| `/source` | 源代码信息 |

## FromContext

标记注解，用于从 MCP 上下文中注入参数。

```python
from typing import Annotated
from nexusx.use_case import FromContext

class SprintService(UseCaseService):
    @query
    async def list_sprints(cls, tenant_id: Annotated[int, FromContext()]) -> list[SprintSummary]:
        ...
```

## build_dto_select

辅助函数，构建查询 DTO 所需字段的 SELECT 语句。

```python
from nexusx import build_dto_select

stmt = build_dto_select(SprintSummary)
stmt = build_dto_select(SprintSummary, where=Sprint.id == sprint_id)
```

> **注意：** 当 ORM 关系使用 `lazy="noload"` 时（ErManager + Resolver 的推荐模式），此函数的收益有限，因为裁剪仅限于标量列。可以用 `select(Entity)` + `DTO.model_validate(entity)` 实现相同效果。仅在 DTO 从宽表中选取少量标量列时，列裁剪才有实际价值。
