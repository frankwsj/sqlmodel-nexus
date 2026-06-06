# ER 图与非 ORM 关系

nexusx 自动发现 SQLModel 实体的 ORM 关系，同时支持声明非 ORM 关系——跨服务调用、计算边、非数据库来源的关系。所有关系都可以通过 ER 图可视化。

## ORM 关系自动发现

创建 `ErManager` 时，它会自动从 SQLAlchemy 元数据中发现所有关系：

```python
from nexusx import ErManager

er = ErManager(base=SQLModel, session_factory=async_session)
```

发现的范围包括：

- SQLModel 实体的 `Relationship` 字段
- `Field(foreign_key=...)` 定义的外键
- 通过 `back_populates` 建立的双向关系

!!! info
    你不需要做任何额外的事——只要 SQLModel 实体有 `Relationship()` 或 `Field(foreign_key=...)` 声明，`ErManager` 就能找到它们。

## 非 ORM 关系声明

对于不存在于数据库中的关系——跨服务调用、计算边、外部 API——用 `Relationship` 在实体上声明：

```python
from nexusx import Relationship

async def tags_loader(task_ids: list[int]) -> list[list[Tag]]:
    """批量加载多个 task 的 tags。"""
    ...

class Task(SQLModel, table=True):
    __relationships__ = [
        Relationship(fk="id", target=list[Tag], name="tags", loader=tags_loader)
    ]
    id: int | None = Field(default=None, primary_key=True)
    title: str
```

### Relationship 参数

| 参数 | 说明 |
|------|------|
| `fk` | 源实体的字段名——DataLoader 用它来收集键值 |
| `target` | 目标类型（`Entity` 或 `list[Entity]`） |
| `name` | 关系名称——用于隐式自动加载匹配 |
| `loader` | DataLoader 类或异步批量函数 |

## ErManager 初始化

你有两种方式：

```python
# 方式 1：传入基类，自动发现所有子类
er = ErManager(base=SQLModel, session_factory=async_session)

# 方式 2：显式传入实体列表
er = ErManager(entities=[Sprint, Task, User], session_factory=async_session)
```

!!! warning
    `base` 和 `entities` 是**互斥的**——你不能同时传两个。

## 自定义关系 + 隐式自动加载

自定义关系使用与 ORM 关系相同的 DataLoader 基础设施，也支持隐式自动加载：

```python
class TagDTO(DefineSubset):
    __subset__ = (Tag, ("id", "name"))

class TaskDTO(DefineSubset):
    __subset__ = (Task, ("id", "title"))
    tags: list[TagDTO] = []   # 名称匹配自定义关系 "tags" → 自动加载
```

只要字段名匹配已注册的关系名，它就会自动加载——不需要写 `resolve_*`。

## 完整示例

```python
from sqlmodel import SQLModel, Field, Relationship, select
from nexusx import ErManager, DefineSubset

# 实体定义
class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str

class Task(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    owner_id: int = Field(foreign_key="user.id")
    owner: User | None = Relationship()

class Sprint(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    tasks: list[Task] = Relationship(back_populates="sprint")

# 初始化
er = ErManager(base=SQLModel, session_factory=async_session)
Resolver = er.create_resolver()
```

## 回顾

- `ErManager` 自动从 SQLAlchemy 元数据中发现 ORM 关系
- 非 ORM 关系通过实体类上的 `__relationships__` 声明
- ORM 和自定义关系都支持 DTO 的隐式自动加载
- `base` 和 `entities` 是互斥的初始化参数

## 下一步

- [ER 图可视化](./er_diagram_visual.zh.md) — 生成 Mermaid ER 图
- [自定义关系](./custom_relationship.zh.md) — 非 ORM 关系的详细用法
- [Core API 模式](./core_api.zh.md) — 使用 ErManager 构建 REST 响应
