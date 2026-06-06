# UseCase + FastAPI

Two ways to serve your `UseCaseService` via FastAPI: **auto-generated routes** (recommended) or **manual thin routes** (for finer control over HTTP semantics).

## Step 1: Auto-Generated Routes

The simplest approach — `create_use_case_router` generates POST routes from your service methods:

```python
from fastapi import FastAPI
from nexusx import UseCaseAppConfig, create_use_case_router

config = UseCaseAppConfig(
    name="project",
    services=[SprintService, TaskService],
)

app = FastAPI()
app.include_router(create_use_case_router(config))
```

This produces endpoints like:

```
POST /api/sprint_service/list_sprints
POST /api/sprint_service/get_sprint
POST /api/task_service/list_tasks
```

The router automatically reads each method's return annotation and sets it as `response_model` — so OpenAPI docs show the correct response types without any extra configuration.

See [UseCase Service](./use_case_service.md) for the full details including `FromContext` parameter injection.

## Step 2: Manual Thin Routes

When you need GET methods, path parameters, 404 handling, or other HTTP-specific behavior — write routes manually. The pattern is the same: routes are thin wrappers, business logic stays in the service.

### Use return annotations for response_model

To keep types in sync with the service, use `get_return_type` to extract the return annotation:

```python
from fastapi import FastAPI, HTTPException
from nexusx import get_return_type

app = FastAPI()

@app.get("/api/sprints", response_model=get_return_type(SprintService.list_sprints), tags=[SprintService.get_tag_name()])
async def get_sprints():
    return await SprintService.list_sprints()

@app.get("/api/sprints/{sprint_id}", response_model=get_return_type(SprintService.get_sprint), tags=[SprintService.get_tag_name()])
async def get_sprint(sprint_id: int):
    result = await SprintService.get_sprint(sprint_id=sprint_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Sprint not found")
    return result
```

If the return type changes in the service, the route's `response_model` updates automatically — no duplicate type declarations.

### OpenAPI grouping

`get_tag_name()` returns the class name as a tag for FastAPI's `/docs`:

```python
SprintService.get_tag_name()  # → "SprintService"
TaskService.get_tag_name()    # → "TaskService"
```

## Which Approach?

| | Auto-generated routes | Manual thin routes |
|---|---|---|
| Setup | One `include_router` call | Write each route |
| HTTP methods | POST only | GET, POST, PUT, DELETE |
| `response_model` | From method return annotation (automatic) | From `get_return_type()` |
| Path parameters | All in request body | Native FastAPI path/query params |
| 404 handling | Service returns `None` | Route raises `HTTPException` |
| Best for | Quick setup, MCP + REST parity | Public APIs needing REST conventions |

## Recap

- `create_use_case_router` auto-generates POST routes — `response_model` from return annotations
- Manual routes give full HTTP control — use `get_return_type()` to keep `response_model` in sync
- Both approaches delegate to the same `UseCaseService` methods — business logic defined once

## Next Steps

- [UseCase Service](./use_case_service.md) — Define UseCaseService classes and MCP integration
- [Core API Mode](../guide/core_api.md) — DTO definition and resolve patterns
