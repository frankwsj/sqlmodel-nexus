"""Shared fixtures and models for nexusx benchmark tests."""

from typing import Optional

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import Field, Relationship, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from nexusx import (
    Collector,
    DefineSubset,
    ErManager,
    SubsetConfig,
)

# ──────────────────────────────────────────────────────────
# Models (all relationships defined with forward references)
# ──────────────────────────────────────────────────────────


class User(SQLModel, table=True):
    __tablename__ = "bench_user"

    id: int | None = Field(default=None, primary_key=True)
    name: str

    tasks: list["Task"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"lazy": "noload", "order_by": "Task.id"},
    )
    posts: list["Post"] = Relationship(
        back_populates="author",
        sa_relationship_kwargs={"lazy": "noload", "order_by": "Post.id"},
    )
    comments: list["Comment"] = Relationship(
        back_populates="author",
        sa_relationship_kwargs={"lazy": "noload", "order_by": "Comment.id"},
    )


class Sprint(SQLModel, table=True):
    __tablename__ = "bench_sprint"

    id: int | None = Field(default=None, primary_key=True)
    name: str

    tasks: list["Task"] = Relationship(
        back_populates="sprint",
        sa_relationship_kwargs={"lazy": "noload", "order_by": "Task.id"},
    )


class Task(SQLModel, table=True):
    __tablename__ = "bench_task"

    id: int | None = Field(default=None, primary_key=True)
    title: str
    done: bool = False
    sprint_id: int = Field(foreign_key="bench_sprint.id")
    owner_id: int | None = Field(default=None, foreign_key="bench_user.id")

    sprint: Optional["Sprint"] = Relationship(back_populates="tasks")
    owner: Optional["User"] = Relationship(back_populates="tasks")


class Post(SQLModel, table=True):
    __tablename__ = "bench_post"

    id: int | None = Field(default=None, primary_key=True)
    title: str
    author_id: int = Field(foreign_key="bench_user.id")

    author: User | None = Relationship(back_populates="posts")
    comments: list["Comment"] = Relationship(
        back_populates="post",
        sa_relationship_kwargs={"lazy": "noload", "order_by": "Comment.id"},
    )


class Comment(SQLModel, table=True):
    __tablename__ = "bench_comment"

    id: int | None = Field(default=None, primary_key=True)
    content: str
    post_id: int = Field(foreign_key="bench_post.id")
    author_id: int = Field(foreign_key="bench_user.id")

    post: Post | None = Relationship(back_populates="comments")
    author: User | None = Relationship(back_populates="comments")


# ──────────────────────────────────────────────────────────
# DefineSubset DTOs (Core API benchmarks)
# ──────────────────────────────────────────────────────────


class UserSummary(DefineSubset):
    __subset__ = SubsetConfig(kls=User, fields=["id", "name"])


class TaskSummary(DefineSubset):
    __subset__ = SubsetConfig(kls=Task, fields=["id", "title", "sprint_id", "owner_id", "done"])
    owner: UserSummary | None = None


class SprintSummary(DefineSubset):
    __subset__ = SubsetConfig(kls=Sprint, fields=["id", "name"])
    tasks: list[TaskSummary] = []
    task_count: int = 0
    contributor_names: list[str] = []

    def post_task_count(self):
        return len(self.tasks)

    def post_contributor_names(self):
        names = {t.owner.name for t in self.tasks if t.owner}
        return sorted(names)


class TaskDetail(DefineSubset):
    __subset__ = SubsetConfig(
        kls=Task,
        fields=["id", "title", "sprint_id", "owner_id", "done"],
        send_to=[("owner", "contributors")],
    )
    owner: UserSummary | None = None
    full_title: str = ""

    def post_full_title(self, ancestor_context=None):
        if ancestor_context is None:
            ancestor_context = {}
        sprint_name = ancestor_context.get("sprint_name", "unknown")
        return f"{sprint_name} / {self.title}"


class SprintDetail(DefineSubset):
    __subset__ = SubsetConfig(
        kls=Sprint,
        fields=["id", "name"],
        expose_as=[("name", "sprint_name")],
    )
    tasks: list[TaskDetail] = []
    contributors: list[UserSummary] = []

    def post_contributors(self, collector=Collector("contributors")):
        return collector.values()


# ──────────────────────────────────────────────────────────
# Entity groups
# ──────────────────────────────────────────────────────────

SPRINT_ENTITIES = [User, Sprint, Task]
BLOG_ENTITIES = [User, Post, Comment]

# ──────────────────────────────────────────────────────────
# Database helpers
# ──────────────────────────────────────────────────────────

SQLITE_URL = "sqlite+aiosqlite:///:memory:"


def _create_session_factory():
    engine = create_async_engine(SQLITE_URL, echo=False)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, sf


async def _setup_tables(engine):
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)


async def _seed_sprint_data(sf, n_users, n_sprints, n_tasks_per_sprint):
    async with sf() as session:
        users = [User(name=f"User_{i}") for i in range(n_users)]
        for u in users:
            session.add(u)
        await session.commit()
        for u in users:
            await session.refresh(u)

        sprints = [Sprint(name=f"Sprint_{i}") for i in range(n_sprints)]
        for s in sprints:
            session.add(s)
        await session.commit()
        for s in sprints:
            await session.refresh(s)

        task_id = 0
        for sprint in sprints:
            for _j in range(n_tasks_per_sprint):
                owner = users[task_id % n_users]
                task = Task(
                    title=f"Task_{task_id}",
                    sprint_id=sprint.id,
                    owner_id=owner.id,
                    done=task_id % 3 == 0,
                )
                session.add(task)
                task_id += 1
        await session.commit()


async def _seed_blog_data(sf, n_users):
    async with sf() as session:
        users = [User(name=f"User_{i}") for i in range(n_users)]
        for u in users:
            session.add(u)
        await session.commit()
        for u in users:
            await session.refresh(u)

        posts = []
        for u in users:
            n_posts = 3 + (hash(u.name) % 3)
            for j in range(n_posts):
                p = Post(title=f"Post_{u.name}_{j}", author_id=u.id)
                session.add(p)
                posts.append(p)
        await session.commit()
        for p in posts:
            await session.refresh(p)

        comments = []
        for i, p in enumerate(posts):
            n_c = 2 + (i % 2)
            for j in range(n_c):
                author = users[(i + j + 1) % n_users]
                c = Comment(content=f"Comment_{i}_{j}", post_id=p.id, author_id=author.id)
                session.add(c)
                comments.append(c)
        await session.commit()


# ──────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────


class _SprintDB:
    """Pre-seeded sprint database for resolver benchmarks."""

    def __init__(self):
        self.engine = None
        self.sf = None
        self.resolver = None
        self._seeded = False

    async def ensure(self, n_users=20, n_sprints=10, n_tasks_per_sprint=20):
        if self._seeded:
            return
        self.engine, self.sf = _create_session_factory()
        await _setup_tables(self.engine)
        await _seed_sprint_data(self.sf, n_users, n_sprints, n_tasks_per_sprint)
        er = ErManager(entities=SPRINT_ENTITIES, session_factory=self.sf)
        self.resolver = er.create_resolver()
        self._seeded = True


class _BlogDB:
    """Pre-seeded blog database for GraphQL benchmarks."""

    def __init__(self):
        self.engine = None
        self.sf = None
        self._seeded = False

    async def ensure(self, n_users=20):
        if self._seeded:
            return
        self.engine, self.sf = _create_session_factory()
        await _setup_tables(self.engine)
        await _seed_blog_data(self.sf, n_users)
        self._seeded = True


@pytest.fixture(scope="session")
def sprint_db():
    return _SprintDB()


@pytest.fixture(scope="session")
def blog_db():
    return _BlogDB()


def pytest_configure(config):
    config.addinivalue_line("markers", "benchmark: mark test as benchmark test")
