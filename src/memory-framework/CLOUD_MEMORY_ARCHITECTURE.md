# Cloud Memory Architecture

This write-up describes how the current local file-backed memory framework can translate into a cloud-backed store behind a chat API, with Azure as the target runtime and Container Apps as the deployment environment.

The goal is not to replace the memory model. The goal is to preserve the current model and swap the storage layer.

## Current Local Model

The framework currently has four main subsystems:

- storage:
  - `MEMORY.md` as a compact index
  - one topic file per durable memory
- recall:
  - scan topic headers
  - select relevant topics
  - surface selected topic bodies into the main turn
- write path:
  - async post-turn extraction
  - deterministic write-time hygiene
- maintenance:
  - background consolidation
  - optional manual consolidation

That decomposition is already the right shape for a cloud-backed system.

## What Should Stay The Same

The important thing to keep is the logical contract:

- a compact index exists for prompt injection
- durable memories exist as topic-level records
- the main turn consumes prepared memory context
- extraction writes memory after the main turn
- consolidation is separate from extraction
- recall loads only small relevant slices, not the whole store

So the cloud version should still think in terms of:

- index
- topic memory records
- scan/select/surface
- extract
- consolidate

The change is only how those things are stored and retrieved.

## Recommended Translation

The cleanest translation is:

- `MEMORY.md` becomes a compact per-scope index record
- each topic file becomes a topic memory record
- the maintenance state file becomes a private framework state record

“Scope” here means whatever unit you want memory to belong to:

- the most likely default for this framework is `{tenant, user}`
- in the future, you may want an additional shared/team layer above user memory
- other possible dimensions include workspace, repo, or agent, but those should stay secondary unless you have a strong product reason

The current filesystem layout:

```text
memory/
  MEMORY.md
  topics/*.md
```

becomes a logical cloud layout:

- one index record per scope
- many topic records per scope
- one framework state record per scope

For this framework, the most practical near-term interpretation of scope is:

- one memory namespace per `{tenant, user}`

If you later introduce a team construct, the clean extension is not to replace user scope, but to add a second shared scope, for example:

- `{tenant, team}` for shared team memory
- `{tenant, user}` for personal memory

At recall time, that would let you compose memory from multiple scopes in priority order, for example:

1. personal user memory
2. shared team memory

while keeping writes explicit about which scope they target.

## Storage-Engine View

The framework should stop depending on files directly and instead depend on a storage interface.

The right abstraction is a `MemoryStore` interface with methods roughly like:

```python
class MemoryStore(Protocol):
    def get_index(self, scope: MemoryScope) -> str: ...
    def save_index(self, scope: MemoryScope, index_text: str) -> None: ...

    def list_topic_headers(self, scope: MemoryScope) -> list[MemoryHeader]: ...
    def get_topics(self, scope: MemoryScope, topic_ids: list[str]) -> list[MemoryTopic]: ...
    def upsert_topic(self, scope: MemoryScope, topic: MemoryTopic) -> None: ...
    def delete_topic(self, scope: MemoryScope, topic_id: str) -> None: ...

    def load_state(self, scope: MemoryScope) -> ConsolidationState: ...
    def save_state(self, scope: MemoryScope, state: ConsolidationState) -> None: ...
```

With that in place, you can support:

- `FileMemoryStore`
- `RedisMemoryStore`
- `PostgresMemoryStore`

without changing the recall/write/maintenance model.

## Redis Mapping

If you want the closest cloud equivalent to the current file model, Redis works well.

Recommended key layout:

- `memory:{tenant}:{user}:index`
  - string
  - stores the rendered `MEMORY.md` equivalent
- `memory:{tenant}:{user}:topic:{topic_id}`
  - hash or JSON record
  - stores one topic memory
- `memory:{tenant}:{user}:topic_ids`
  - set or sorted set
  - stores all topic ids for the scope
- `memory:{tenant}:{user}:state`
  - hash or JSON record
  - stores maintenance counters and timestamps

If team memory is added later, mirror the same structure under a separate namespace, for example:

- `memory:{tenant}:team:{team_id}:index`
- `memory:{tenant}:team:{team_id}:topic:{topic_id}`
- `memory:{tenant}:team:{team_id}:topic_ids`
- `memory:{tenant}:team:{team_id}:state`

That keeps user and team memories separate in storage while still allowing the recall layer to merge them.

Topic record fields should include:

- `topic_id`
- `name`
- `description`
- `type`
- `content`
- `updated_at`
- `created_at`
- `version`

Optional useful fields:

- `last_selected_at`
- `last_extracted_at`
- `source_count`
- `confidence`
- `volatility`

### Why Redis Fits

Redis is a good fit when:

- chat requests need very low-latency memory reads
- the memory store is prompt-oriented
- reads are much more frequent than writes
- the memory footprint per scope is relatively small
- background consolidation needs simple coordination

This is especially attractive for:

- a few dozen to a few thousand topic memories per scope
- frequent recall
- light post-turn writes

### What To Change In The Current Design For Redis

In the local framework, `MEMORY.md` is still treated as a human-readable operational artifact. In Redis, I would keep it as a rendered string for prompt injection, but I would think of it as derived state rather than the primary semantic source of truth.

That means:

- topic records are the real durable memory
- the index record is a compact, normalized projection of those topics

This is cleaner than trying to preserve literal markdown-file editing semantics.

## Postgres Mapping

If memory is becoming durable product data rather than just fast chat state, Postgres is usually the better primary store.

Recommended model:

- `memory_topics`
  - one row per topic memory
- `memory_indexes`
  - one row per scope for the rendered compact index
- `memory_maintenance_state`
  - one row per scope

Suggested `memory_topics` columns:

- `scope_type`
- `scope_id`
- `tenant_id`
- `topic_id`
- `name`
- `description`
- `memory_type`
- `content`
- `created_at`
- `updated_at`
- `version`
- `deleted_at` nullable if you want soft delete

For the initial version, `scope_type` would usually just be `user`, and `scope_id` would be the user id inside a tenant. If team memory is added later, `scope_type` can expand to `team` without changing the rest of the model.

Advantages over Redis as the only store:

- stronger durability
- easier migrations
- better auditing
- easier operational recovery
- better support for admin/reporting tools

For long-lived production memory, Postgres is the more conservative default.

## Recommended Production Shape

For a prototype or smaller deployment:

- Azure Managed Redis only

For a more durable production shape:

- Postgres as the system of record
- Redis as the hot recall cache

That split works well because the current framework already has a natural divide:

- semantic source of truth: topic memories
- prompt-optimized fast state: compact index and selected headers

In that architecture:

- extraction writes to Postgres
- recall reads mostly from Redis
- consolidation reads/writes Postgres
- after writes or consolidation, Redis is refreshed

## Azure-Specific Recommendation

If you are on Azure Container Apps, the best cloud-native options are:

- Azure Managed Redis for low-latency memory state
- Azure Database for PostgreSQL Flexible Server for durable records

Azure-specific guidance:

- prefer Azure Managed Redis, not legacy Azure Cache for Redis, for new work
- use managed identity or Entra auth where supported
- keep the API in one Container App
- run consolidation either in:
  - a second worker Container App, or
  - a Container Apps Job, or
  - the API app itself if the background load is light

The framework does not need session-specific transcript machinery here. The same time-plus-activity maintenance gates still work.

## API Shape Behind The Chat Endpoint

The chat API should not expose raw storage semantics to the model.

The server-side flow should stay roughly:

1. receive user turn
2. load compact index for the scope
3. load topic headers for the scope
4. run selector
5. fetch selected topic bodies
6. run main model with:
   - compact index
   - selected topic bodies
7. return assistant response
8. enqueue post-turn extraction
9. if maintenance gate is open, enqueue consolidation

So the API contract to the frontend stays simple:

- frontend sends user message
- backend handles memory loading and background memory work

If team/shared memory is introduced later, the API should still keep the same shape. The difference is that the backend would assemble recall context from more than one scope, usually:

- user scope first
- then team scope

with user memory taking precedence when there is conflict.

## Write Path In A Cloud Store

The write path should remain lightweight and mostly mechanical.

Recommended write sequence:

1. extraction receives recent turn transcript
2. extraction decides whether to create, update, or forget a topic
3. backend upserts the topic record
4. backend runs deterministic write hygiene:
   - validate topic schema
   - avoid exact duplicates where possible
   - regenerate or normalize the index projection
   - update maintenance counters

The key design point is the same as the current framework:

- write path owns mechanical hygiene
- consolidation owns semantic cleanup

## Recall Path In A Cloud Store

The recall path should stay query-time and selective.

Recommended sequence:

1. fetch lightweight topic headers only
2. run selector on:
   - user query
   - filename/id
   - description
   - type
   - maybe `updated_at`
3. fetch full bodies only for selected topics
4. inject:
   - compact index
   - surfaced selected topic bodies

That avoids loading all memories into the prompt or all bodies into application memory.

## Consolidation In A Cloud Store

Consolidation should remain a background semantic pass with an audit input.

Recommended shape:

1. audit current store
2. pass audit summary plus current memory records to the consolidate agent
3. let the model decide merges, contradiction fixes, and deletions
4. apply deterministic post-pass normalization
5. reset maintenance counters

The audit should stay code-driven, not model-driven.

Good audit outputs:

- broken index pointers
- duplicate index entries
- orphan topic records
- malformed topic schema
- exact duplicate topic bodies
- size pressure

## State And Scheduling

The current framework’s maintenance state file translates directly into a state record.

Suggested state fields:

- `last_consolidated_at`
- `writes_since_consolidation`
- `distinct_topic_files_touched_since_consolidation`

If you want better cloud observability, add:

- `last_extracted_at`
- `last_activity_at`
- `last_index_regenerated_at`
- `last_consolidation_status`

The current scheduling model still makes sense in cloud form:

- run extraction after each turn
- opportunistically check consolidation gates after writes
- run consolidation only when:
  - enough time has passed
  - enough activity or pressure has accumulated

## Redis-Only vs Postgres+Redis

### Redis-only

Use this when:

- you want the simplest architecture
- the memory is mostly operational agent state
- strict durability is not the top concern
- you want very fast iteration

Tradeoff:

- simpler
- faster
- weaker system-of-record posture

### Postgres + Redis

Use this when:

- memory matters as durable application data
- you want stronger operational safety
- you may need admin tooling, audits, or future migrations

Tradeoff:

- more moving parts
- better long-term fit

## Recommended Path For This Framework

If extending the current codebase, I would do it in this order:

1. introduce `MemoryStore`
2. keep the existing file store as `FileMemoryStore`
3. move recall/write/maintenance code to depend only on `MemoryStore`
4. add `RedisMemoryStore`
5. optionally add `PostgresMemoryStore`
6. if needed later, add a Redis cache in front of Postgres

That lets you preserve the framework’s current shape while changing only the backend implementation.

## Practical Azure Recommendation

Given your setup:

- Azure
- API in Container Apps
- chat-oriented workload

I would recommend:

### Short-term

- Azure Managed Redis
- one API Container App
- either:
  - a second worker Container App for consolidation, or
  - in-process background extraction and consolidation if load is modest

### Medium-term

- Postgres as source of truth
- Azure Managed Redis as fast recall cache

That is the best balance of:

- simplicity
- latency
- durability
- future-proofing

## Bottom Line

The memory model does not need to change for cloud deployment.

What changes is:

- file paths become scope-aware records
- file reads/writes become store operations
- the index becomes a rendered projection
- maintenance state becomes a private state record

The best general translation is:

- keep the current framework architecture
- introduce a storage interface
- start with Redis if you want simplicity
- prefer Postgres plus Redis if this is becoming durable product memory
