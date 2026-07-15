# The koyu-workspace manual

Operational manual for coding agents working a koyu workspace. Laws apply
to every task, routes cover the common ones. The workspace is simpler than
the runtime: it stores experiments, ingests recordings, and syncs to the
cloud, so this manual is short.

One mental model matters. The store is plain files under `$KOYU_HOME`, and
you work it at two levels. Entity lifecycle (projects, runs, manifests)
goes through the server's HTTP API and the `koyu` verbs. The folders those
entities live in are a coding surface: helping the user with robot learning
experiments means writing real code and real files inside project and run
directories.

## Laws

1. **Entities are born through the API.** Create projects, runs, and
   manifests via the server routes or `koyu` verbs, and treat
   `project.json`, `run.json`, and `catalog.json` as the store's ledger,
   written only by the store. Every other file inside an entity's folder
   is yours to create and edit freely.
2. **The running server owns the store.** While it is up, route metadata
   mutations through it. The CLI sync verbs already do, discovering the
   server through its state file, which is why the server starts first.
3. **Provenance rides the sidecar.** Episodes arrive carrying whatever
   context the runtime recorded, and ingest maps it into the store,
   links eval manifests to their source runs, and rolls up success rates.
   Context is ensured on the runtime side before recording (runtime
   AGENTS.md, law 7); at ingest there is nothing to add.
4. **Ingest is idempotent.** Each bundle either files completely or stays
   in the outbox with a printed reason. Re-running a sweep is always safe.
5. **Sync needs a token, public reads need none.** `koyu clone` of a
   public project works anonymously. `sync-push` and `sync-pull` of your
   own entities authenticate via `KOYU_TOKEN`, a `--token` flag, or
   `.koyu/credentials.json`.

## Routes

### Ingest a robot's recordings

Arm the outbox once (`PUT /api/ingest/config` with the runtime's
`data-recordings` path, or the gear on the Datasets page), then `koyu
ingest` or the Ingest button. Provenance, manifest membership, run links,
and success rollups all happen inside the sweep (law 3). Bundles that fail
stay put and say why (law 4).

### Clone a project from koyu.dev

Start the server, then `koyu clone proj_<id>`. All files and runs arrive,
checkpoints included, with fresh local ids and lineage back to the source.
Use the new local ids for anything downstream, especially recording
context on the runtime side; the cloud ids belong to the cloud.

### Work inside project and run folders

Each run records one experiment, and runs nest so iterations can branch.
Put the experiment's code, configs, checkpoints, and results directly in
the run's folder; the Files panels in the frontend show whatever is there.
Create the run first (law 1), then treat its folder like any working
directory.

### Link runs to manifests

Ingest links eval manifests to their source runs automatically (law 3).
For everything else, the link API pairs any run with any manifest
(`add_run_manifest` via the server, or the picker on the run page), and
the run's page then shows the dataset card.

### Sync with the cloud

`koyu sync-push project|run|manifest <id>` sends an entity up, and
`sync-pull` brings one down. When authentication fails, help the user get
a token accepted: they mint one at koyu.dev settings, and it reaches the
sync engine through `export KOYU_TOKEN=…`, a `--token` flag, or a
`.koyu/credentials.json` shaped `{"cloud_bearer_token": "…"}` (law 5).
Verify with a small `sync-pull` before pushing anything large.

### Build a browser surface

The wiring primer for any browser surface, the four data primitives and
their liveness rules, lives at the top of `frontend/src/lib/useBridge.ts`,
which is also the reference client.
