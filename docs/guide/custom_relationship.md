# Custom Relationships

SQLModel's `Relationship` and `Field(foreign_key=...)` cover database-level connections. But real applications also need relationships that don't live in the database:

- **Cross-service calls**: Load associated data from external APIs
- **Computed edges**: Associations based on business logic rather than FKs
- **Non-database sources**: Caches, search engines, file systems
- **Intermediate tables**: Many-to-many via join tables that don't map to simple FKs

This page shows how to declare these relationships and integrate them with the same auto-loading mechanism that ORM relationships use.

## Step 1: Write a Batch Loader Function

The loader receives a list of key values and returns the corresponding results. Write it before declaring the relationship:

```python
from nexusx import build_list

# List target: one key → list of entities
async def tags_loader(task_ids: list[int]) -> list[list[Tag]]:
    """Batch load tags for multiple tasks."""
    async with get_session() as session:
        stmt = (
            select(Tag, TaskTag.task_id)
            .join(TaskTag)
            .where(TaskTag.task_id.in_(task_ids))
        )
        rows = (await session.exec(stmt)).all()
        return build_list(rows, task_ids, lambda row: row[1], lambda row: row[0])

# Single target: one key → one entity
async def user_loader(user_ids: list[int]) -> dict[int, User]:
    users = await fetch_users(user_ids)
    return {u.id: u for u in users}
```

The return type determines the relationship direction:

| Target type | Loader returns | Example |
|-------------|---------------|---------|
| `User` | `dict[int, User]` | One user per key |
| `list[Tag]` | `list[list[Tag]]` | List of tags per key |

## Step 2: Declare the Relationship on Your Entity

Add a `__relationships__` list to your SQLModel entity:

```python
from nexusx import Relationship

class Task(SQLModel, table=True):
    __relationships__ = [
        Relationship(fk="id", target=list[Tag], name="tags", loader=tags_loader)
    ]
    id: int | None = Field(default=None, primary_key=True)
    title: str
```

### Relationship parameters

| Parameter | Description |
|-----------|-------------|
| `fk` | Field name on the source entity — DataLoader uses it to collect key values |
| `target` | Target type: `Entity` for single, `list[Entity]` for list |
| `name` | Relationship name — used for matching DTO fields during auto-loading |
| `loader` | DataLoader class or async batch function |

### Single vs list target

```python
# Single: fk value → one entity
Relationship(fk="owner_id", target=User, name="owner", loader=user_loader)

# List: fk value → list of entities
Relationship(fk="id", target=list[Tag], name="tags", loader=tags_loader)
```

## Step 3: Use in DTOs — Same as ORM Relationships

Custom relationships integrate with implicit auto-loading identically to ORM relationships:

```python
from nexusx import DefineSubset

class TagDTO(DefineSubset):
    __subset__ = (Tag, ("id", "name"))

class TaskDTO(DefineSubset):
    __subset__ = (Task, ("id", "title"))
    tags: list[TagDTO] = []   # Name "tags" matches custom relationship → auto-loaded
```

The connection point is the `name` parameter — the DTO field name must match it.

!!! tip
    The field name in your DTO must match the `name` parameter of the `Relationship` declaration. As long as the four conditions for implicit auto-loading are met, custom relationships are handled automatically.

## Recap

- Custom relationships extend beyond the ORM — cross-service, computed, non-database, many-to-many
- Declare them in `__relationships__` with `fk`, `target`, `name`, and `loader`
- Write the loader first, then declare the relationship, then use it in DTOs
- They integrate with implicit auto-loading just like ORM relationships — the `name` parameter is the connection point

## Next Steps

- [ER Diagram](./er_diagram.md) — Visualizing all relationships (ORM + custom)
- [Core API Mode](./core_api.md) — Using custom relationships in REST DTOs
