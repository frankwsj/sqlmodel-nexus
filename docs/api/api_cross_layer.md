# Cross-layer Data Flow API

Share data between ancestor and descendant nodes using ExposeAs, SendTo, and Collector.

## ExposeAs

Expose ancestor fields to descendant nodes, making them accessible via `ancestor_context`.

```python
from typing import Annotated
from nexusx import ExposeAs

class SprintDTO(DefineSubset):
    __subset__ = (Sprint, ("id", "name"))
    name: Annotated[str, ExposeAs('sprint_name')]
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | `str` | Key name in `ancestor_context` |

### Accessing in Descendants

Descendants can access exposed values through the `ancestor_context` parameter:

```python
class TaskDTO(DefineSubset):
    def post_full_title(self, ancestor_context):
        return f"{ancestor_context['sprint_name']} / {self.title}"
```

The `ancestor_context` is a `dict` collecting all values exposed by ancestors through `ExposeAs`.

!!! tip
    Use cross-layer data flow when child nodes need ancestor context (like sprint names, permission info, or tenant IDs) but you want to avoid passing them explicitly through every method call. This is particularly useful for computed fields that depend on tree structure.

## SendTo

Send descendant field values to an ancestor's Collector for aggregation.

```python
from typing import Annotated
from nexusx import SendTo

class TaskDTO(DefineSubset):
    __subset__ = (Task, ("id", "title", "owner_id"))
    owner: Annotated[UserDTO | None, SendTo('contributors')] = None
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `collector_name` | `str` | Name of the target Collector |

## Collector

Receive values sent by descendants via `SendTo` in `post_*` methods.

```python
from nexusx import Collector

class SprintDTO(DefineSubset):
    contributors: list[UserDTO] = []

    def post_contributors(self, collector=Collector('contributors')):
        return collector.values()
```

### Methods

| Method | Description |
|--------|-------------|
| `values()` | Returns a list of all collected values |

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Collector name, matching the `SendTo` target name |

!!! tip
    Use SendTo and Collector when you need to aggregate data from multiple descendants — like collecting all contributors across tasks, gathering all tags from posts, or building unique sets from nested objects. This pattern keeps parent nodes aware of their descendant data without tight coupling.
