<!-- DO NOT EDIT. Generated from _index.md by scripts/render-tutorials.py. Edit _index.md and run `python3 scripts/render-tutorials.py`. -->

Imagine you manage a building and want to know — the instant it happens — when any room becomes uncomfortable: too hot, too cold, or stuffy with CO2. You don't want to poll sensors on a timer or wire up a stream processor by hand. You just want to describe what "uncomfortable" means and have something watch every room, floor, and the whole building for you, continuously.

This tutorial builds a **Building Comfort** monitoring demo on **Drasi Server**. A PostgreSQL database holds a building made of floors and rooms, each room reporting `temperature`, `humidity`, and `co2`. You'll start Drasi Server with a single configuration, watch a live dashboard light up, and then change room readings and see everything react in real time — without writing any application code, and **without building a bespoke web UI**. Instead of a hand-written dashboard, the demo uses Drasi Server's built-in **dashboard reaction**.

**What you'll build:** a running Drasi Server that connects to PostgreSQL and reacts to room sensor changes in real time, assembled from Drasi's three core building blocks:

**Sources** → **Continuous Queries** → **Reactions**

- **Sources**: Connect to your data sources
- **Continuous Queries**: Define what changes matter
- **Reactions**: Take action automatically

| Step | What You'll Do | Time |
| ---- | ------------- | ---- |
| **[Step 1: Set Up Your Environment](#step-1-of-4-set-up-your-environment)** | Build matching Server and plugin binaries from the existing checkouts | Depends on build cache |
| **[Step 2: Run the Demo](#step-2-of-4-run-the-demo)** | One command starts PostgreSQL and Drasi Server | 3 min |
| **[Step 3: Open the Dashboard](#step-3-of-4-open-the-dashboard)** | Watch comfort levels and alerts live | 2 min |
| **[Step 4: Drive Change](#step-4-of-4-drive-change)** | Break, reset, and simulate rooms — and watch Drasi react instantly | 5 min |
| **[How It Works](#how-it-works)** | Understand the source, the six queries, the synthetic joins, and the dashboard | 5 min |

> **Before you begin**
>
> - **Terminals:** you'll use two. **Terminal 1** runs the demo (it stays in the foreground). Use **Terminal 2** for the helper scripts that change data.
> - **Working directory:** run every command from the tutorial directory (`tutorials/building-comfort/`). The dev container opens there automatically; if you're running locally, `cd tutorials/building-comfort` first.
> - **Platform:** use macOS, Linux, or WSL with Python 3.11 or newer. All commands below use the same Python helper; there are no separate shell-specific implementations.
> - **Ports:** the Drasi Server API is on `8380`, the dashboard is on `3000`, and PostgreSQL is published on `5732`.
> - **Runtime:** this tutorial builds the ComputationGraph version of Drasi Server, not a published Server release. Other tutorials have not necessarily been migrated.

## Step 1 of 4: Set Up Your Environment
### Use the existing source checkouts

Keep these repositories beside one another, on their matching
`agentofreality-parallel-computation-graph` branches:

```text
workspace/
  drasi-core/
  drasi-server/
  learning-drasi-server/
```

The build helper does not clone repositories, switch branches, download released
Drasi binaries, or change dependencies. Server must reference `../drasi-core/lib`
in its Cargo manifest. The ordinary PostgreSQL and reaction interfaces remain
supported: they run inside ComputationGraph without requiring native graph YAML.

For a local build, install Python 3.11+, Rust through rustup, a C/C++ compiler,
CMake, Clang/libclang, pkg-config, jq with its development library, OpenSSL
development files, and `protoc`. Use a Rust toolchain supported by the matching
checkouts; this tutorial's qualification uses **Rust 1.95.0**. PostgreSQL runs in
**Podman with a Compose provider**. Start the Podman machine first on macOS.
Docker Compose is also supported when you explicitly set `CONTAINER_ENGINE=docker`.

On Debian/Ubuntu the native prerequisites are:

```bash
sudo apt-get install build-essential cmake clang libclang-dev pkg-config \
  libjq-dev libssl-dev protobuf-compiler python3
```

On macOS, use the Xcode command-line tools and Homebrew's `cmake`, `llvm`,
`pkg-config`, `jq`, `openssl@3`, and `protobuf`. If linking cannot locate jq, set
`JQ_LIB_DIR="$(brew --prefix jq)/lib"` and `LIBRARY_PATH` to that directory.
Do not enable bundled jq or build the entire workspace with `--all-features`.

From `learning-drasi-server/`:

```bash
cd tutorials/building-comfort
RUSTUP_TOOLCHAIN=1.95.0 python3 scripts/demo.py build
```

If the Core checkout has no workspace `Cargo.lock` yet, run
`cargo generate-lockfile --manifest-path ../../../drasi-core/Cargo.toml`
from the tutorial directory before building.

This builds Server and exactly four plugins from the sibling Core checkout:
PostgreSQL source, PostgreSQL bootstrap, dashboard reaction, and log reaction.
It uses `drasi-server/target` by default, then copies a matching set into the
tutorial's private `.runtime/builds/` directory. `.runtime/build.json` records
repository revisions, working-tree status, compiler version, and artifact hashes.
Rebuild after changing Server or Core.

The dashboard's web assets are embedded in its plugin. This tutorial does not
require the separate Server management UI or a Node.js build.

### Optional local dev container

Open this repository in VS Code, choose **Reopen in Container**, and select
**Drasi Server - Building Comfort Tutorial**. Keep all three checkouts present
first: this configuration mounts their parent directory and installs the build
prerequisites. Its post-create script runs the same local build, with a
container-specific Cargo target directory.

This source-based setup is **not a one-click Codespaces or release-ZIP setup**.
Those environments need the matching Core and Server checkouts too. The former
`0.2.0-preview` downloads are deliberately no longer offered for this tutorial.

### Optional settings

Copy `.env.example` to `.env` to change ports or select Docker. The helper reads
literal `NAME=value` entries; exported variables take precedence. Change
`POSTGRES_PORT` and `POSTGRES_HOST_PORT` together. Services bind to loopback by
default; do not expose the demo credentials or dashboard publicly.

The new database uses the `building-comfort-cg` Compose project. It does not
reuse or delete the old tutorial's database. Server writes its local runtime
files under `.runtime/`, not the former `data/` directory.

## Step 2 of 4: Run the Demo
Everything runs from a single configuration file, `server-config.yaml`. In **Terminal 1**, start the demo:

```bash
python3 scripts/demo.py start-demo
```

The helper verifies the local artifact hashes before touching the database.
It starts PostgreSQL, seeds an empty database with one building, three floors,
and nine comfortable rooms, and runs Server in the foreground. Repeating the
command preserves existing database contents; it does not drop tables or volumes.

Server loads only the four prepared local plugins. `autoInstallPlugins: false`
prevents release downloads. The helper passes `--skip-verification` specifically
for these locally built, hash-checked plugins, which do not have registry
signatures. It does not change global plugin-verification settings or use the
global plugin cache.

Wait for the helper's readiness message, not merely the API-started log line:

```text
Building Comfort READY: ComputationGraph; source, six queries and two reactions running.
```

Leave this running. Everything else happens from **Terminal 2** (or your browser).

> **Stopping and resetting**
>
> Press **Ctrl+C** in Terminal 1 to stop Server. To stop PostgreSQL while preserving
> its data, run `python3 scripts/demo.py cleanup`. Add `--volumes` only when you
> intend to delete this demo's database. No command kills other Server processes.

## Step 3 of 4: Open the Dashboard
Drasi Server's dashboard reaction hosts a live web dashboard — there's no separate
app to build or run. After the **Building Comfort READY** message, open:

```text
http://localhost:3000
```

In the local dev container, port `3000` is forwarded automatically and appears
as **Comfort Dashboard** in VS Code's **Ports** panel. Select the predefined
**Building Comfort** dashboard if the dashboard list is shown first.

You'll see the **Building Comfort** dashboard:

- **Building Comfort** (the large panel) — the building grouped by floor, with each room's comfort level and sensor readings. Every room starts at comfort `46` (comfortable).
- **Building Comfort** KPI and **gauge** — the building's overall comfort level.
- **Comfort Alerts** and **Floor Alerts** — empty for now; rooms and floors appear here only when they need attention.
- **Floor Comfort** — a table of each floor's comfort level.

The dashboard updates the instant the data changes — no refreshing. Let's make something change.

## Step 4 of 4: Drive Change
With Terminal 1 running the demo and the dashboard open, use **Terminal 2** to change room readings and watch Drasi react.

> **No middle tier — the scripts just write to the database**
>
> The data-changing commands below run ordinary SQL `UPDATE` statements against
> PostgreSQL. They do not call Server or publish artificial query results. Drasi
> observes those changes through logical replication, updates the queries, and
> sends result changes to the dashboard.

### Break a room

Push a single room out of the comfortable band (sets `temperature = 40`, `humidity = 20`, `co2 = 700`):

```bash
python3 scripts/demo.py break-room room_01_01_01
```

**Room 01** on **Floor 01** changes from comfort `46` to `4`, and its label
becomes blue (too cold). Floor 01 becomes `32`, and building comfort becomes
approximately `41.3333`. Room and floor alerts appear, but **no building alert**
appears: the building average is still within 40-50. Terminal 1 logs the alerts.

### Reset a room (or all rooms)

Return a room — or the whole building — to comfortable defaults (`70 / 40 / 10`):

```bash
# Reset one room
python3 scripts/demo.py reset-room room_01_01_01

# Reset every room
python3 scripts/demo.py reset-room
```

The alerts clear and the building returns to green.

### Set custom values

Try partial degradation — make a room too hot without touching CO2:

```bash
# set-room <room_id> <temperature> <humidity> <co2>
python3 scripts/demo.py set-room room_01_02_03 82 40 10
```

Starting with the other rooms reset, this gives room comfort `58`, floor comfort
`50`, and building comfort approximately `47.3333`. **Only the room alerts**:
the floor is exactly on the comfortable upper boundary.

To see a building alert too, reset everything and break two rooms:

```bash
python3 scripts/demo.py reset-room
python3 scripts/demo.py break-room room_01_01_01
python3 scripts/demo.py break-room room_01_01_02
```

Floor 01 becomes `18`, and building comfort becomes approximately `36.6667`.
All three kinds of alert now have results. Reset all rooms to clear them.

### Let it run hands-free

To keep the dashboard alive without typing, run the simulator. It picks a random room every few seconds and assigns new readings, so comfort levels rise and fall and alerts come and go on their own:

```bash
python3 scripts/demo.py simulate

# Or make just three changes, one second apart:
python3 scripts/demo.py simulate 1 --count 3
```

Press **Ctrl+C** to stop the simulator, then run `python3 scripts/demo.py reset-room`.
Reset-all sends a single multi-row SQL update; every changed room must reach the
queries and dashboard.

### Stop and restart without losing your source data

Set a room to an uncomfortable value, stop Server with Ctrl+C, and run
`python3 scripts/demo.py start-demo` again. PostgreSQL retains your readings.
The memory-backed queries bootstrap from those current rows, and the dashboard
returns to the same state. Layout edits and query/API changes are not persisted
by this tutorial configuration.

This is a normal restart and fresh bootstrap, **not** a claim of durable query
indexes, crash-safe browser delivery, or exactly-once external effects.

## How It Works
Everything you just ran is described by the single `server-config.yaml`. Here's what each part does.

### The Source

```yaml
sources:
  - kind: postgres
    id: building-facilities
    autoStart: true

    # Connection (supplied via environment variables, with defaults)
    host: "${POSTGRES_HOST:-localhost}"
    port: ${POSTGRES_PORT:-5732}
    database: "${POSTGRES_DATABASE:-building_comfort}"
    user: "${POSTGRES_USER:-drasi_user}"
    password: "${POSTGRES_PASSWORD:-drasi_password}"
    sslMode: prefer

    # Tables to monitor (PascalCase so node labels match the queries)
    tables:
      - Building
      - Floor
      - Room

    # Logical replication slot + publication
    slotName: drasi_building_comfort_slot
    publicationName: drasi_building_comfort_pub

    # Primary key of each table, so Drasi can track row identity
    tableKeys:
      - table: Building
        keyColumns:
          - id
      - table: Floor
        keyColumns:
          - id
      - table: Room
        keyColumns:
          - id

    # Load the rows that already exist when the server starts
    bootstrapProvider:
      kind: postgres
```

The PostgreSQL source connects with the credentials above (provided via environment variables, with sensible defaults) and uses **logical replication (CDC)** to stream changes from the `Building`, `Floor`, and `Room` tables. `tableKeys` tells Drasi the primary key of each table so it can track row identity across changes. The bootstrap provider loads the rows that already exist when the server starts; after that, every `UPDATE` you make (via the helper scripts) flows to Drasi as a change. The table names are quoted and PascalCase so the node labels Drasi sees match the queries exactly: `(r:Room)`, `(f:Floor)`, `(b:Building)`. For every option the source accepts, see [Configure the PostgreSQL Source](https://drasi.io/drasi-server/how-to-guides/configuration/configure-sources/configure-postgresql-source/).

### The Continuous Queries

Each query computes a **comfort level** with the same formula. A value between **40 and 50** is comfortable; the seed values (70°F, 40%, 10 ppm) give `50 + (70-72) + (40-42) + 0 = 46`.

```cypher
floor( 50 + (r.temperature - 72) + (r.humidity - 42)
      + CASE WHEN r.co2 > 500 THEN (r.co2 - 500) / 25 ELSE 0 END )
```

There are six queries:

| Query | What it returns |
| ----- | --------------- |
| `building-comfort-ui` | One row per room with its comfort level — the feed that drives the dashboard view |
| `building-comfort-level-calc` | The building's overall comfort level |
| `floor-comfort-level-calc` | Each floor's average comfort level |
| `room-alert` | Only the rooms whose comfort is outside 40–50 |
| `floor-alert` | Only the floors whose average comfort is outside 40–50 |
| `building-alert` | The building, when its overall comfort is outside 40–50 |

#### Synthetic joins connect the entities

PostgreSQL knows `Room.floor_id` references `Floor.id` through a foreign key, but Drasi doesn't read foreign keys. Instead, each query **declares** the relationships it needs as synthetic joins, so the Cypher can walk from room to floor to building:

```yaml
sources:
  - sourceId: building-facilities
    nodes:
      - Room
      - Floor
      - Building
joins:
  - id: PART_OF_FLOOR
    keys:
      - label: Room
        property: floor_id
      - label: Floor
        property: id
  - id: PART_OF_BUILDING
    keys:
      - label: Floor
        property: building_id
      - label: Building
        property: id
```

With those joins declared, a query can match the whole hierarchy:

```cypher
MATCH (r:Room)-[:PART_OF_FLOOR]->(f:Floor)-[:PART_OF_BUILDING]->(b:Building)
```

#### Aggregating up the hierarchy

Half of the queries don't just read rooms — they **roll comfort levels up** the building. In a Continuous Query, an aggregate such as `avg()` inside a `WITH` groups by whatever non-aggregated values travel alongside it, exactly like SQL's `GROUP BY`.

**One stage — average a floor's rooms.** `floor-comfort-level-calc` keeps the floor `f` in the `WITH`, so `avg()` produces one value per floor:

```cypher
WITH f, floor( 50 + (r.temperature - 72) + ... ) AS RoomComfortLevel
WITH f, avg(RoomComfortLevel) AS ComfortLevel
RETURN f.id AS FloorId, ComfortLevel
```

**Two stages — average the averages.** `building-alert` aggregates twice. Carrying `f, b` groups the first `avg()` by floor; dropping `f` from the next `WITH` widens the grouping so the second `avg()` rolls the floor averages up into a single building level:

```cypher
WITH f, b, avg(RoomComfortLevel) AS FloorComfortLevel   // rooms  -> floor
WITH b,    avg(FloorComfortLevel) AS ComfortLevel        // floors -> building
```

**Filtering on an aggregate.** The `floor-alert` and `building-alert` queries place a `WHERE` *after* the aggregation — like SQL's `HAVING` — so a floor or the building only shows up while its average is outside the comfortable band:

```cypher
WITH f, avg(RoomComfortLevel) AS ComfortLevel
WHERE ComfortLevel < 40 OR ComfortLevel > 50
RETURN f.id AS FloorId, ComfortLevel
```

Because these are *continuous* queries, the aggregates are maintained **incrementally**: when one room's reading changes, Drasi recomputes only the affected floor and building averages and emits just that change — it never rescans every room.

### The Dashboard Reaction

```yaml
reactions:
  - kind: dashboard
    id: building-comfort-dashboard
    queries:
      - building-comfort-ui
      - building-comfort-level-calc
      # ...
    port: 3000
    predefinedDashboards:
      - id: building-comfort
        name: Building Comfort
        widgets:
          # ...
```

The dashboard reaction subscribes to the queries and streams their changes to the browser over a WebSocket. A **predefined dashboard** is seeded on startup, so the layout is ready the first time you open it. Most of the panels are **Markdown widgets** that use the reaction's Handlebars helpers (`groupBy`, `each`, `gt`/`lt`) to lay out the building from the `building-comfort-ui` rows, plus a KPI and gauge for the overall level and Markdown widgets for the alert lists. Because the queries only emit *changes*, the dashboard updates the instant a room's comfort changes — no polling. The full set of widget types and configuration options is documented in [Configure the Dashboard Reaction](https://drasi.io/drasi-server/how-to-guides/configuration/configure-reactions/configure-dashboard-reaction/).

For example, the centerpiece **Building Comfort** panel is a single Markdown widget. Its template groups the `building-comfort-ui` rows by floor with `groupBy`, loops the rooms with `each`, and uses the `gt`/`lt` helpers to pick a status emoji per comfort level. Here is the widget's `template`:

```handlebars
{{#groupBy rows "FloorName"}}
### {{@key}}
{{#each this}}
- **{{this.RoomName}}** — comfort **{{this.ComfortLevel}}**
    {{#if (gt this.ComfortLevel 50)}}
      🔴 too hot
    {{else}}
      {{#if (lt this.ComfortLevel 40)}}
        🔵 too cold
      {{else}}
        🟢 comfortable
      {{/if}}
    {{/if}}
    · 🌡️ {{this.Temperature}}°F  💧 {{this.Humidity}}%  🫧 {{this.CO2}} ppm
{{/each}}
{{/groupBy}}
```

And the reaction renders it live:

<img src="images/dashboard-building-view.png" width="820" alt="The Building Comfort widget: rooms grouped by floor, each tagged with a comfort level and a green, red, or blue status emoji">

### Where ComputationGraph fits

The named instance `building-comfort-server` owns one ComputationGraph. Its
PostgreSQL source supplies all six query transformers; the dashboard and log
reactions consume their result changes. The ordinary configuration interfaces
are adapters into that graph, not a second execution engine.

You do not need an `executionMode` field, an enablement flag, explicit ports and
pipes, or a rewrite of the comfort formula to use this runtime.

Check the running components at any time:

```bash
python3 scripts/demo.py check
```

The check requires the selected instance to report `runtime: "computationGraph"`
and `running: true`, with the source, all six queries and both reactions running,
and the predefined dashboard available. It is a readiness check, not proof that
every input has finished processing.

To compare every query and dashboard snapshot with the current PostgreSQL rows
without modifying data, run `python3 scripts/verify_demo.py`. The
[migration notes](migration.md) also describe the repeatable, data-changing
acceptance exercises.

> **Inspect the queries directly (optional)**
>
> You can also query Drasi Server's REST API while the demo runs — see `requests.http` for ready-made requests, for example:
>
> ```text
> GET http://localhost:8380/api/v1/instances/building-comfort-server/queries/building-comfort-ui/results
> GET http://localhost:8380/api/v1/instances/building-comfort-server/queries/room-alert/results
> ```

## Clean Up
When you're finished, stop Drasi Server with **Ctrl+C** in Terminal 1, then remove the database container:

```bash
# Stop containers, keep data
python3 scripts/demo.py cleanup

# Only when you intend to delete this demo's database:
python3 scripts/demo.py cleanup --volumes
```

Cleanup checks this tutorial's ownership labels and never kills processes by
name. The old tutorial's containers, volumes and files are not touched. Local
builds and the build record remain available for another run.

## Migration Notes
See [Migrating Building Comfort to ComputationGraph](migration.md) for the exact
runtime, plugin, configuration, helper and documentation changes, what stayed
the same, and the acceptance checks used for this tutorial.

## What You Learned
- **Sources** connect Drasi Server to live data — here, PostgreSQL via Change Data Capture.
- **Continuous Queries** with **synthetic joins** let you model relationships (room → floor → building) and compute derived values (comfort levels) that stay current automatically.
- **Reactions** turn query changes into action. The **dashboard reaction** gave you a live, configurable UI with zero application code — no bespoke web app required.
- Because Drasi emits only what *changed*, everything updates the instant the data does, with no polling.

From here, try editing the comfort formula or the dashboard widgets in `server-config.yaml`, adding a new alert query, or pointing the dashboard at your own data.
