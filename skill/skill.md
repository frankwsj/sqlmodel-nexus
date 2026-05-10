---
name: sqlmodel-nexus-4phase
description: 基于 sqlmodel-nexus 的四阶段开发模式，从 Schema 建模到 API 响应组装再到 TS SDK 的完整项目构建流程。
argument-hint: "[项目路径] 创建四阶段项目的目标目录"
---

# sqlmodel-nexus 四阶段开发模式

基于 sqlmodel-nexus 的渐进式开发方法论。项目在一个 `src/` 目录下逐步演进，每个阶段在上一阶段基础上新增代码。

| Phase | 职责 | 产出 |
|-------|------|------|
| **Phase 0** | 需求确认 | 实体 + 关系 + 聚合根 + 用例方法（与用户反复确认） |
| **Phase 1** | Schema + ER Diagram + 聚合根入口 + mock seed | models + db(engine + session) + database(seed) + voyager |
| **Phase 2** | Loader 实现 | models 方法体实现，GraphQL 可查询 |
| **Phase 3** | UseCase 响应组装 + MCP | dtos + services + REST + MCP + Voyager 补充 services |
| **Phase 4** | OpenAPI spec → TS SDK | 端到端 SDK |

## 核心原则

- **需求确认是 Phase 0，必须反复与用户确认后才能进入 Phase 1**（详见下方「Phase 0: 需求确认」）
- 非功能模块与业务模块解耦，业务概念不侵入基础设施层
- **每个阶段必须暂停，展示产出物，等用户确认后再进入下一阶段**
- Phase 间递进：同一项目目录下逐步丰富，只新增不修改已有代码

## Phase 0: 需求确认（必做）

在写任何代码之前，必须与用户逐项确认以下内容。每一项都需要用户明确认可后才算完成。

### Step 0-1: 术语与实体定义

逐一列出所有业务实体，每个实体说明：

- **业务含义**（一句话，团队无歧义）
- **核心字段**（名称 + 类型 + 语义说明，不需要穷举，但关键属性不能遗漏）
- **字段约束**（唯一、非空、枚举值、联合唯一等）

用表格形式呈现，方便用户逐行确认。

### Step 0-2: 实体关系

用文本 ER 图展示实体间关系，每条关系标明：

- 方向（1:N / N:1 / M:N）
- 业务含义（如「会话包含多条消息」）
- 是否需要中间实体

```
User ──1:N──→ Participant
Conversation ──1:N──→ Message
...
```

**必须与用户确认关系方向和基数是否正确。**

### Step 0-3: 聚合根

明确哪个（或哪些）实体是聚合根。聚合根决定：

- 主要的业务入口（从哪个实体开始查询）
- @query / @mutation 挂在哪些实体上
- Phase 3 的 service 划分依据

### Step 0-4: 业务域划分 + 用例方法

**先划分业务域（Service），再按域列出用例方法。**

业务域按功能边界划分，不按实体划分。例如 `auth`（认证）、`chat`（聊天）、`order`（订单）等。
每个业务域对应一个 service 目录，后续 Phase 2/3 的 methods.py / service.py / dtos.py 都按此组织。

列出每个业务域的用例方法，每个方法说明：

- **方法名**（动词开头，如 `create_conversation`、`list_messages`）
- **业务意图**（一句话，如「创建群聊并自动将创建者加入为 owner」）
- **挂载实体**（挂在哪个 Entity 的 @query / @mutation 上，供 GraphQL 使用）
- **关键参数**（列出参数名和含义，不需要完整签名）

示例格式：

| 业务域 | 方法名 | 业务意图 | 挂载实体 | 关键参数 |
|--------|--------|----------|----------|----------|
| auth | register | 注册新用户 | User | username, nickname, password |
| auth | login | 登录返回 JWT | User | username, password |
| chat | create_conversation | 创建会话 | Conversation | type, creator_id, name |
| chat | list_messages | 查询会话消息（分页） | Conversation | conversation_id, before_id, limit |

**用例方法不需要实现细节，但必须逻辑自洽**：
- mutation 的参数是否足以完成操作
- 创建类 mutation 是否有遗漏的副作用（如自动创建关联记录）
- 查询类方法是否覆盖了核心场景

### Step 0-4a: GraphQL 定位

GraphQL 是辅助开发测试和 AI 测试的接口，不是正式 API。

业务方法的定义和挂载关系：

```
service/<domain>/methods.py  ← 独立定义业务逻辑（核心）
        ↓ 挂载                    ↓ 挂载
  Entity @query/@mutation    UseCaseService @query/@mutation
  (GraphQL 辅助测试)          (REST + MCP 正式接口)
```

- Phase 2：方法体在 `service/<domain>/methods.py` 中实现，`models.py` 通过直接赋值挂载到 Entity
- Phase 3：同一个方法挂载到 UseCaseService（REST/MCP 使用），DTO 转换在 Service 层完成

### Step 0-5: 第三方库确认

列出项目中涉及的非业务功能领域（认证、实时推送、文件存储、数据迁移等），对每个领域：

- **说明候选方案**（推荐成熟第三方库 vs 手写实现）
- **给出推荐理由**（社区活跃度、维护状态、与 FastAPI/SQLModel 的兼容性）
- **必须调查用户提到的第三方库的当前维护状态**（避免选用已停止维护的库）

用表格形式呈现：

| 功能领域 | 推荐方案 | 理由 | 备注 |
|----------|----------|------|------|
| 认证 | ... | ... | ... |
| ... | ... | ... | ... |

**注意事项**：
- 优先使用 FastAPI 生态内的主流方案，减少集成风险
- 如果用户指定了某个库，必须先调查其维护状态和兼容性，发现问题要及时告知用户并提供替代方案
- 对于 sqlmodel-nexus 已覆盖的领域（ORM、GraphQL、MCP），不再重复讨论

**必须与用户确认每个领域的选型后才能继续。**

### Step 0-6: 检查清单

全部确认后，向用户展示汇总，确保以下问题已回答：

- [ ] 所有实体和字段是否完整，约束是否清晰？
- [ ] 实体关系方向和基数是否正确？
- [ ] 聚合根是否明确？
- [ ] 业务域划分是否合理？
- [ ] 核心用例是否覆盖主要业务场景，逻辑是否自洽？
- [ ] 第三方库选型是否确认，维护状态是否已调查？
- [ ] 是否有明显的遗漏或边界情况需要讨论？

**全部确认后才能进入 Phase 1。**

## 参考实现

读取本 skill 目录下 `template/` 中的代码作为生成参考。严格遵守 template 中的文件结构、import 风格和命名约定。

## 项目结构

单项目渐进演进，每个 Phase 在上一阶段基础上新增文件：

```
src/
├── models.py       # Phase 1 骨架 → Phase 2 从 methods 挂载 @query/@mutation
├── db.py           # Phase 1（engine + session factory，不依赖 models）
├── database.py     # Phase 1（mock seed，依赖 db + models）
├── service/        # Phase 2 新增 methods.py，Phase 3 补充 service.py/dtos.py
│   ├── auth/       # 按业务域划分（非按实体）
│   │   ├── methods.py  # Phase 2: 独立业务方法
│   │   ├── dtos.py     # Phase 3: DTO
│   │   ├── service.py  # Phase 3: UseCaseService
│   │   └── spec.md     # Phase 3: 服务说明
│   └── chat/
│       ├── methods.py
│       ├── dtos.py
│       ├── service.py
│       └── spec.md
├── main.py         # 逐步扩展（voyager → graphql → rest → mcp）
└── router/         # Phase 3 新增（可选，按需拆分）
```

## 四阶段定义

### Phase 1: Schema + ER Diagram + 聚合根入口

**目标**: 定义实体、关系、查询/变更契约，用 ER diagram 可视化供团队讨论。

**新增/修改文件**:
- `db.py` — aiosqlite engine + session_factory（不导入 models，避免循环依赖）
- `models.py` — SQLModel 实体 + Relationship + `@query`/`@mutation`（从 `db.py` 导入 `async_session`）
- `database.py` — mock seed data（从 `db.py` 导入 engine/session，从 `models.py` 导入实体）
- `main.py` — FastAPI + Voyager（ER diagram 可视化）+ GraphiQL

**关键模式**:
- SQLModel 实体 + Relationship 声明关系方向
- 每个 Model 必须有 docstring 说明业务含义，每个 Field 必须有 `description` 说明字段语义
- `@query` / `@mutation` 方法体用 `pass` + docstring 描述业务意图
- mock seed data 用于讨论数据样本是否合理（数量、关联关系、边界值）
- Voyager 通过 `create_use_case_voyager(services=[], er_manager=er)` 展示 ER diagram

**阶段结束 → 暂停确认**:
- 展示实体、关系、聚合根划分
- **展示 mock seed data，与用户确认数据样本的合理性和覆盖度**
- 启动服务，Voyager 中查看 ER diagram
- 展示 `/schema` 的 GraphQL SDL
- 等用户全部确认后再进入 Phase 2

### Phase 2: 方法实现 + Entity 挂载

**目标**: 按业务域实现独立方法，挂载到 Entity 的 @query/@mutation，GraphQL 可查询。

**新增/修改文件**:
- `service/<domain>/methods.py` — 独立业务方法实现（核心逻辑，不含 @query/@mutation 装饰器）
- `models.py` — 从 methods 导入并通过 `Entity.method = query(fn)` / `Entity.method = mutation(fn)` 挂载

**关键模式**:
- 业务方法在 `service/<domain>/methods.py` 中定义，为普通 async 函数（非 classmethod）
- `models.py` 只负责挂载：`User.register = mutation(register)`
- GraphQL 作为辅助测试接口，`@query`/`@mutation` 装饰器在挂载时应用
- 挂载代码放在 Entity class 定义之后、ErManager 之前

**测试验收描述（先确认测试集，再做具体实现）**:

进入 Phase 2 编码之前，必须先与用户确认测试验收集。对每个 `@query` / `@mutation` 方法列出：

| 方法 | 测试场景 | 预期结果 | 验证方式 |
|------|----------|----------|----------|
| method_a | 正常场景 | 返回预期数据 | GraphQL query |
| method_a | 边界/异常 | 错误提示 | GraphQL query |

验证方式统一通过 GraphQL query/mutation 在 GraphiQL 中执行，不写自动化测试。

**阶段结束 → 暂停确认**:
- 启动服务，在 GraphiQL 中执行查询，验证关系加载正确
- 确认 seed 数据合理、Loader 行为符合预期

### Phase 3: UseCase 响应组装 + MCP

**目标**: 按 API 用例组装响应结构。DefineSubset 隐藏内部字段，UseCaseService 统一业务入口。

**新增/修改文件**:
- `service/<entity>/spec.md` — 服务目的、用途、需求、变更记录
- `service/<entity>/dtos.py` — DefineSubset DTOs
- `service/<entity>/service.py` — UseCaseService
- `router/` — FastAPI REST 端点（调用 Service）
- `main.py` — 挂载 REST router + MCP + Voyager 补充 services

**关键模式**:
- `DefineSubset` + `SubsetConfig` 定义响应 DTO（字段选择、FK 隐藏）
- `ErManager` + `Resolver` 自动加载关系（implicit auto-load）
- `UseCaseService` 统一业务逻辑入口（同时服务 MCP 和 FastAPI）
- `@query` / `@mutation` 装饰器标记服务方法
- `build_dto_select()` 只查 DTO 需要的列
- `create_use_case_voyager()` 可视化服务结构
- `create_use_case_mcp_server()` + `UseCaseAppConfig` 暴露给 AI agent
- REST 端点通过 `tags=[Service.get_tag_name()]` 分组

**阶段结束 → 暂停确认**:
- 启动服务，测试 REST 端点返回数据正确
- 访问 Voyager 确认服务可视化完整
- 测试 MCP 端点可被发现和调用

### Phase 4: OpenAPI → TS SDK

**目标**: 从 FastAPI OpenAPI spec 生成 TypeScript SDK。

提示用户执行：
```bash
npx openapi-typescript http://localhost:8000/openapi.json -o sdk/schema.d.ts
```

**阶段结束 → 暂停确认**:
- 验证生成的 TS 类型与实际 API 一致

## 阶段间变化对照

| 方面 | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|------|---------|---------|---------|---------|
| 实体 | SQLModel 骨架 + docstring + mock seed | 方法体实现 | 继承 Phase 2 | - |
| 关系 | Relationship 声明 | DataLoader 实现 | DefineSubset 隐藏 FK | - |
| 查询 | pass 占位 | SQLAlchemy async | UseCaseService 封装 | - |
| API | Voyager(ER diagram) + GraphiQL | GraphQL | GraphQL + REST + Voyager(+services) + MCP | TS SDK |
| 响应 | N/A | 完整实体 | DefineSubset DTO | OpenAPI spec |

## 踩坑经验

1. **engine/session 必须独立为 `db.py`** — `models.py` 需要 `async_session`，`database.py` 需要 models，放在同一文件会导致循环导入。`db.py` 只放 engine + session_factory，不导入任何 model
2. **`pyproject.toml` 必须配置 `packages = ["src"]`** — hatchling 默认按项目名找目录，`src/` 布局需要显式指定 `[tool.hatch.build.targets.wheel]`
3. **不要在 DefineSubset 文件中使用 `from __future__ import annotations`** — 会使类型注解变字符串，SubsetMeta 无法检测 Annotated 元数据
4. **DTO 字段类型必须用 DTO 类型** — 不能直接用 SQLModel 实体，否则 TypeError
5. **列表关系需要 order_by** — 分页功能要求 `sa_relationship_kwargs={"order_by": "Entity.column"}`
6. **ErManager base 和 entities 互斥** — 不能同时提供
7. **目录命名不能以数字开头** — Python 模块名限制
8. **UseCaseService 只有被 @query/@mutation 装饰的 async classmethod 会被发现** — 普通方法不会暴露
9. **build_dto_select → dict(row._mapping) → DTO 构造** — 这是 Core API 的标准查询模式
10. **每个 Model 必须有 docstring，每个 Field 必须有 description** — Phase 1 就要确保语义清晰，description 会传递到 OpenAPI spec
11. **每个 service 子目录必须包含 spec.md** — 记录服务目的、用途、方法需求、DTO 说明和变更记录，方便团队理解服务边界

## 需求文档管理

每次使用 skill 时，必须在项目根目录下创建 `spec/` 目录，按以下规则组织需求文档：

### 目录命名

```
spec/<编号>-<需求简述>/
```

- **编号格式**: `YY-MM-DD` + 两位序号，如 `250510-01`
- **需求简述**: 英文短横线连接，如 `chat-demo`

示例: `spec/250510-01-chat-demo/`

### 文件结构

```
spec/<编号>-<需求简述>/
├── story.md        # 用户原始需求 + Overview Design
├── phase0.md       # 需求确认
├── phase1.md       # Schema + ER Diagram
├── phase2.md       # Loader 实现
├── phase3.md       # UseCase + MCP
└── phase4.md       # TS SDK
```

### 文件内容格式

每个 phase 文件分两个部分：

```markdown
# Phase N: <阶段标题>

## 需求说明

（记录用户在对话中提出的原始需求、约束条件和确认结论）

## 实现描述

（记录该阶段的具体技术实现方案、产出文件和关键决策）
```

### 写入时机

| 文件 | 写入时机 |
|------|----------|
| story.md | 用户首次描述需求时记录原始表述；Phase 0 确认后补充 Overview Design（见下方说明） |
| phase0.md | Phase 0 全部确认后，进入 Phase 1 之前 |
| phase1.md | Phase 1 完成并经用户确认后 |
| phase2.md | Phase 2 完成并经用户确认后 |
| phase3.md | Phase 3 完成并经用户确认后 |
| phase4.md | Phase 4 完成并经用户确认后 |

## 执行步骤

当用户要求创建四阶段项目时：

1. **创建 spec 目录**: 用户首次描述需求时，在项目根目录创建 `spec/<编号>-<需求简述>/`，将用户原始需求写入 `story.md`，预建 phase0 ~ phase4 空文件
2. **Phase 0 需求确认**: 按 Step 0-1 ~ 0-6 逐步与用户确认实体、关系、聚合根、用例方法、第三方库 → 确认后写入 `phase0.md` → **补充 `story.md` 的 Overview Design 部分** → **用户全部确认后才继续**
3. **创建项目结构**: 目录 + pyproject.toml（依赖 sqlmodel-nexus）
4. **Phase 1**: 生成 db.py + models.py + database.py(mock seed) + main.py(voyager) → 展示 ER diagram + SDL + seed data → 写入 `phase1.md` → **暂停等用户确认**
5. **Phase 2**: 先列出测试验收集与用户确认 → 补充 models 方法体 → 启动服务 → GraphiQL 查询验证 → 写入 `phase2.md` → **暂停等用户确认**
6. **Phase 3**: 新增 dtos.py + services.py + router → 启动服务 → 测试 REST + Voyager + MCP → 写入 `phase3.md` → **暂停等用户确认**
7. **Phase 4**: 提示 openapi-typescript 命令和 SDK 使用模式 → 写入 `phase4.md` → **暂停等用户确认**

### story.md 的 Overview Design 部分

Phase 0 全部确认后、进入 Phase 1 之前，在 `story.md` 中补充 `## Overview Design` 部分，内容包含：

- **业务流程**：核心用户操作路径（用文本流程图）
- **实体关系**：ER 图（文本格式）
- **聚合根**：明确入口实体
- **关键设计决策**：第三方库选型、分页策略、幂等策略等（表格形式）
- **四阶段产出**：每个 Phase 的预期交付物概要

目的：让团队在进入 Phase 1 之前对系统全貌有清晰共识。
