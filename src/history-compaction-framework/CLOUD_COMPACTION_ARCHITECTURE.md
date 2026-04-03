# Cloud Compaction Architecture

This write-up describes how the current local file-backed history compaction framework can translate into a cloud-backed system behind a chat API, with Azure Container Apps as the target runtime.

The goal is not to replace the compaction model. The goal is to preserve the current model and swap the storage and runtime substrate.

## Current Local Model

The framework currently has five main pieces:

- raw history:
  - append-only `history.jsonl`
  - one completed turn record per run
- compaction state:
  - `collapse_state.json`
  - committed spans, staged spans, pressure markers, calibration, and recovery diagnostics
- projection:
  - provider-facing history is built on demand from raw turns plus committed spans
- background staging:
  - older eligible turn ranges are summarized asynchronously and staged for later use
- synchronous bounded recovery:
  - if request pressure is too high and staged inventory is insufficient, the framework can pause and summarize more before continuing

That is already the right logical shape for a cloud-backed version.

## What Should Stay The Same

The important contract to preserve is:

- raw history remains canonical
- committed spans only rewrite the provider-facing view
- staged spans remain out-of-band until committed
- preflight token budgeting is based on the projected request view, not the raw transcript
- background staging remains separate from synchronous recovery
- the main turn still consumes a prepared provider-facing history, not raw storage records directly

So the cloud version should still think in terms of:

- raw turn log
- compaction state
- projected history
- background staging
- bounded synchronous recovery

The change is only where those things live and how they are coordinated across replicas.

## Recommended Cloud Translation

The cleanest translation is:

- one compaction namespace per `{tenant_id, user_id}`
- one append-only raw turn stream per namespace
- one current compaction state record per namespace
- one optional projected-history cache per namespace

For the current product shape, the most practical scope is:

- one compaction namespace per `{tenant_id, user_id}`

If the product later adds multiple concurrent chats per user, the clean extension is:

- `{tenant_id, user_id, conversation_id}`

The framework should stop depending on local files directly and instead depend on a store abstraction, something like:

```python
class ConversationCompactionStore(Protocol):
    def load_recent_turns(self, scope: ConversationScope, *, limit: int | None = None) -> list[TurnRecord]: ...
    def append_turn(self, scope: ConversationScope, turn: TurnRecord) -> None: ...

    def load_compaction_state(self, scope: ConversationScope) -> CollapseState: ...
    def save_compaction_state(self, scope: ConversationScope, state: CollapseState, *, expected_version: int | None = None) -> None: ...

    def load_projected_cache(self, scope: ConversationScope) -> list[dict] | None: ...
    def save_projected_cache(self, scope: ConversationScope, payload: list[dict], *, ttl_seconds: int | None = None) -> None: ...

    def acquire_scope_lock(self, scope: ConversationScope, *, ttl_seconds: int) -> LockToken | None: ...
    def release_scope_lock(self, scope: ConversationScope, token: LockToken) -> None: ...
```

With that in place, the current local design becomes the equivalent of:

- `FileConversationCompactionStore`

and the cloud version can evolve behind:

- `RedisConversationCompactionStore`
- `PostgresConversationCompactionStore`
- or a composed `Postgres + Redis` implementation

## Storage-Engine View

The framework should preserve the same logical decomposition and only swap the store backend.

The right storage responsibilities are:

- raw turns:
  - append-only durable conversation records
- compaction state:
  - the latest committed spans, staged spans, calibration, counters, and last recovery result
- projected cache:
  - an optional prompt-optimized cached rendering of the current projected history
- coordination:
  - per-scope locking and version checks so multiple replicas do not corrupt the state machine

The key design point is:

- the compaction manager and engine should not speak Redis or Postgres directly
- they should speak a store interface

That keeps the compaction model stable while the deployment substrate changes.

## Redis Mapping

Redis is the right hot operational layer for this system.

Recommended use of Redis:

- current compaction state
- projected-history cache
- short-lived coordination locks
- optional recent-turn cache

Recommended key layout:

- `compaction:{tenant}:{user}:state`
  - current serialized `CollapseState`
- `compaction:{tenant}:{user}:projected`
  - cached provider-facing projected history
- `compaction:{tenant}:{user}:lock`
  - short-lived coordination lock for write-side work
- `compaction:{tenant}:{user}:turns:recent`
  - optional cache of recent turn payloads if recent-history reads become hot

If conversation scope is later introduced, extend the namespace cleanly:

- `compaction:{tenant}:{user}:{conversation}:state`
- `compaction:{tenant}:{user}:{conversation}:projected`
- `compaction:{tenant}:{user}:{conversation}:lock`

### Why Redis Fits

Redis is a good fit when:

- projected-history reads need low latency
- the current compaction state is small and frequently read
- locks need short-lived coordination semantics
- the projected cache is derived and can be refreshed cheaply

Redis is especially attractive here because the projected history is prompt-oriented state, not deeply relational application data.

### Why Redis Is Not Enough By Itself

Redis is not the preferred sole source of truth once restart survival matters materially.

Redis-only can work for a bootstrap phase, but it has weaker system-of-record semantics for:

- append-only transcript history
- recovery from partial write failures
- auditing
- replaying compaction state over time
- durable restart survival guarantees

So Redis fits best as:

- hot state
- cache
- coordination

not as the preferred long-term system of record for compaction history.

## Postgres Mapping

Postgres is the right durable system of record for this design once the framework needs restart survival and stronger operational safety.

Recommended durable records:

- raw turn records
- persisted compaction state snapshots
- optional recovery and audit metadata

Suggested relational shape:

### `conversation_turns`

One row per completed turn, keyed by:

- `tenant_id`
- `user_id`
- `turn_id`

Recommended columns:

- `tenant_id`
- `user_id`
- `turn_id`
- `timestamp`
- `user_text`
- `messages_json`
- `estimated_turn_payload_tokens`
- `actual_input_tokens`
- `actual_output_tokens`
- `request_count`

This table should be append-only in normal operation.

### `conversation_compaction_state`

One row per `{tenant_id, user_id}` namespace.

Recommended columns:

- `tenant_id`
- `user_id`
- `state_json`
- `version`
- `updated_at`

The `state_json` payload should contain:

- committed spans
- staged spans
- health counters
- calibration
- last recovery result
- pressure markers

For this memo, JSONB is the right recommendation. There is no need to over-normalize span arrays or recovery metadata in the first write-up.

The important correctness feature is:

- `version` should support optimistic writes

That version becomes the durable concurrency boundary even if Redis is used as the fast coordination layer.

## Recommended Production Shape

The best Azure target shape for this framework is:

- Postgres as system of record
- Redis as hot state, projected-history cache, and coordination layer
- one API Container App
- background staging starting in-process

For the current scale envelope:

- a few hundred tenants
- a couple dozen users per tenant

this is operationally reasonable without adding more Azure infrastructure yet.

This gives you:

- low-latency request-time projection reads
- durable restart survival
- a clean replayable source of truth
- a concurrency model that can work across replicas

## Container Apps Runtime Model

The recommended starting runtime shape is:

- one API Container App
- in-process post-turn staging
- in-process bounded synchronous recovery

That keeps the system simple while the product and workload are still modest.

The main request path stays:

1. load compaction state
2. load required turn history
3. build projected request history
4. commit staged spans if needed
5. optionally run bounded synchronous recovery
6. execute the main model
7. append the new raw turn
8. refresh hot state
9. trigger background staging

Later evolution options:

- a second worker Container App for heavier background staging or maintenance
- a Container Apps Job for maintenance, backfills, or repair work

Those are useful later, but they are not the right default starting point for the current scale and complexity.

## Concurrency and Coordination

Because the same `{tenant_id, user_id}` history may be updated by multiple replicas at once, per-scope coordination is a real requirement.

Without coordination, replicas can race on:

- turn append order
- staged-span creation
- staged-to-committed promotion
- calibration updates
- last-recovery state

The recommended design is:

- Postgres row version is the correctness boundary
- Redis lock is the operational fast-path to reduce collisions

In practice that means:

1. acquire a short-lived Redis lock for `{tenant_id, user_id}`
2. read the current Postgres compaction state and version
3. perform append, stage, commit, or recovery updates
4. write back with an expected Postgres version
5. release the Redis lock

The Redis lock should not be the only correctness mechanism. It reduces contention, but the durable safety boundary should still be a versioned Postgres write.

This is the cleanest fit for Container Apps because:

- replicas can scale horizontally
- lock hold times are short
- most write-side operations are scoped to one `{tenant, user}` namespace

## Restart Survival

There are two reasonable paths to discuss.

### Redis-only Bootstrap

This is acceptable for early experimentation when:

- you want the simplest architecture
- you already only have Redis
- the cost of losing or repairing some history is acceptable

Tradeoffs:

- weaker durability posture
- restart survival depends on Redis persistence configuration
- still lacks clean system-of-record semantics for transcripts and state replay

Redis-only is a valid stepping stone, but it should be treated as a bootstrap architecture, not the preferred durable end state.

### Postgres + Redis Target

This is the preferred target once restart survival matters materially.

Why:

- raw turns are durably stored
- compaction state is durably stored
- projected history can always be rebuilt
- replay and auditing become straightforward
- replica coordination has a clearer correctness boundary

So the practical recommendation is:

- if restart survival matters materially, treat `Postgres + Redis` as the target architecture
- if speed of initial delivery matters more right now, `Redis-only` is a defensible first step, but only with the expectation that it will be replaced

## Read Path and Write Path

The request-time flow should stay high-level and selective.

Recommended read path:

1. load current compaction state
2. load recent and required raw turns
3. optionally read the cached projected history from Redis
4. build or refresh the projected request view
5. commit staged spans if guard-band pressure requires it
6. optionally run bounded synchronous recovery
7. send the resulting projected request history to the main model

Recommended post-turn write path:

1. append the new raw turn durably to Postgres
2. update compaction state durably if needed
3. refresh the hot Redis state and projected cache
4. enqueue or run background staging

The important design point is the same as in the local framework:

- raw history remains canonical
- projected history remains derived

## Azure-Specific Recommendation

For Azure Container Apps, the best default service choices are:

- Azure Database for PostgreSQL Flexible Server
- Azure Managed Redis

Azure-specific guidance:

- use Azure Managed Redis, not the older Azure Cache for Redis naming/model for new work
- use managed identity where the service supports it and where your driver stack makes it practical
- otherwise use Container Apps secrets and configuration for connection settings
- keep the API in one Container App first

Optional later additions:

- a second worker Container App
- a Container Apps Job for maintenance or repair work

This memo should not assume Blob Storage, Cosmos DB, or Service Bus are required for the initial design.

## Recommended Migration Path

The cleanest evolution path is:

1. introduce `ConversationCompactionStore`
2. keep the current local file-backed store for the example
3. add a Postgres-backed durable store
4. add Redis hot-state, projected-cache, and lock support
5. later, externalize heavier staging or maintenance workers if needed

That path lets you preserve the compaction model while swapping the substrate underneath it.

## Bottom Line

The compaction model does not need to change for Azure deployment.

What changes is:

- files become scope-aware records
- local reads and writes become store operations
- projected history becomes a cached derived view
- concurrency becomes an explicit design concern across replicas
- restart survival becomes a storage-layer responsibility rather than a local-filesystem side effect

For this framework, the best Azure target is:

- Postgres as durable source of truth
- Redis as hot state and coordination layer
- one API Container App to start
- in-process background staging first

If you need the shortest path, Redis-only is a reasonable bootstrap option. If restart survival and operational safety matter materially, `Postgres + Redis` is the right destination.
