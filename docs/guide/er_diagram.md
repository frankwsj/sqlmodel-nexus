# ER Diagram & Non-ORM Relationships

nexusx auto-discovers ORM relationships from your SQLModel entities and lets you declare non-ORM relationships for cross-service calls, computed edges, and non-database sources. All relationships can be visualized through ER diagrams.

The central piece is `ErManager` — it discovers, registers, and manages all relationships in your application.

## Step 1: Auto-Discover ORM Relationships

### What does ErManager discover?

When you pass a SQLModel base class to `ErManager`, it scans all subclasses and discovers relationships from SQLAlchemy metadata:

```python
from nexusx import ErManager

er = ErManager(base=SQLModel, session_factory=async_session)
```

Given these entities:

```python
from sqlmodel import SQLModel, Field, Relationship

class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    posts: list["Post"] = Relationship(back_populates="author")

class Post(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    author_id: int = Field(foreign_key="user.id")
    author: User | None = Relationship(back_populates="posts")
```

ErManager discovers:

| Source | Example |
|--------|---------|
| `Relationship()` fields | `Post.author`, `User.posts` |
| `Field(foreign_key=...)` | `Post.author_id → User.id` |
| `back_populates` | Bidirectional link between `Post.author` and `User.posts` |

!!! info
    You don't need to do anything special — if your SQLModel entities have `Relationship()` or `Field(foreign_key=...)` declarations, `ErManager` will find them.

### Two initialization options

```python
# Option 1: Pass a base class — auto-discover all subclasses
er = ErManager(base=SQLModel, session_factory=async_session)

# Option 2: Explicitly pass an entity list
er = ErManager(entities=[Sprint, Task, User], session_factory=async_session)
```

!!! warning
    `base` and `entities` are **mutually exclusive** — you can't pass both.

Use Option 1 when all your entities share a common base (the common case). Use Option 2 when you want fine-grained control over which entities are registered.

## Step 2: Add Non-ORM Relationships

Not all relationships live in the database. Cross-service calls, computed edges, many-to-many via join tables — these need explicit declaration using `__relationships__` on your entity:

```python
from nexusx import Relationship

class Task(SQLModel, table=True):
    __relationships__ = [
        Relationship(fk="id", target=list[Tag], name="tags", loader=tags_loader)
    ]
    id: int | None = Field(default=None, primary_key=True)
    title: str
    owner_id: int = Field(foreign_key="user.id")
    owner: User | None = Relationship()        # ORM — auto-discovered
```

Here `owner` is an ORM relationship (auto-discovered), while `tags` is a custom relationship (declared via `__relationships__`). After initialization, ErManager knows about both:

```python
er = ErManager(base=SQLModel, session_factory=async_session)
# Task.owner   → ORM, auto-discovered
# Task.tags    → custom, declared in __relationships__
```

Both types behave identically downstream — same DataLoader infrastructure, same auto-loading in DTOs.

For details on writing loaders, declaration parameters, and DTO integration, see [Custom Relationships](./custom_relationship.md).

## How Relationships Get Used

Once registered in ErManager, your relationships power three features:

| Feature | How it uses relationships |
|---------|--------------------------|
| **Core API** | DTO fields matching a relationship name are auto-loaded — no `resolve_*` needed |
| **GraphQL** | The resolver traverses relationship edges and batch-loads data via DataLoader |
| **ER Diagram** | Both ORM and custom relationships appear in Mermaid output and Voyager |

### Preview: Core API auto-loading

```python
from nexusx import DefineSubset

class TagDTO(DefineSubset):
    __subset__ = (Tag, ("id", "name"))

class TaskDTO(DefineSubset):
    __subset__ = (Task, ("id", "title"))
    tags: list[TagDTO] = []   # Name matches "tags" relationship → auto-loaded
```

See [Core API Mode](./core_api.md) for the full picture.

## Recap

- `ErManager` auto-discovers ORM relationships from SQLAlchemy metadata — no extra configuration needed
- Non-ORM relationships are declared via `__relationships__` — see [Custom Relationships](./custom_relationship.md) for details
- ORM and custom relationships coexist on the same entity and use the same DataLoader infrastructure

## Next Steps

- [Custom Relationships](./custom_relationship.md) — How to write loaders, declare relationships, and use them in DTOs
- [Core API Mode](./core_api.md) — Build REST responses using auto-loaded relationships
- [ER Diagram Visualization](./er_diagram_visual.md) — Generate Mermaid ER diagrams and interactive Voyager views
