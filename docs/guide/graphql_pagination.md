# GraphQL Pagination

List relationships support automatic pagination, implemented via the ROW_NUMBER window function.

## Enabling Pagination

Two conditions:

1. Add `order_by` to the list relationship
2. Enable pagination when creating GraphQLHandler

```python
class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    posts: list["Post"] = Relationship(
        back_populates="author",
        sa_relationship_kwargs={"order_by": "Post.id"},
    )

handler = GraphQLHandler(
    base=SQLModel,
    session_factory=async_session,
    enable_pagination=True,
)
```

## Query Syntax

```graphql
{
  userGetAll {
    name
    posts(limit: 3, offset: 0) {
      items { title }
      pagination { has_more total_count }
    }
  }
}
```

### Response Structure

```json
{
  "userGetAll": [
    {
      "name": "Alice",
      "posts": {
        "items": [
          { "title": "First Post" },
          { "title": "Second Post" },
          { "title": "Third Post" }
        ],
        "pagination": {
          "has_more": true,
          "total_count": 15
        }
      }
    }
  ]
}
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | `Int` | Number of items per page |
| `offset` | `Int` | Offset (starting from 0) |

## Pagination Type

| Field | Type | Description |
|-------|------|-------------|
| `has_more` | `Boolean!` | Whether more data exists |
| `total_count` | `Int!` | Total record count |

## Implementation

The framework uses SQL `ROW_NUMBER()` window function for pagination:

```sql
SELECT * FROM (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY id) as rn
  FROM post
  WHERE user_id IN (...)
) WHERE rn > offset AND rn <= offset + limit
```

This approach fetches both paginated data and total count in a single query.

## Notes

- **List relationships require order_by**: Relationships without `order_by` will not generate pagination support
- **order_by format**: Use the `"Entity.column"` format (string reference)
- Pagination only applies to list relationships (ONETOMANY / MANYTOMANY)

## Next Steps

- [Auto Query](./graphql_auto_query.md) — Skip @query for auto-generated queries
- [Core API Mode](./core_api.md) — DTO building for REST endpoints
