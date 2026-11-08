# LangGraph / LangChain implementation status

## Accepted target

Implement P0–P5 from the approved plan: freeze the working baseline; unify CLI and
evaluation through RuntimePort; extract shared runtime services; add a LangChain
client preserving the JSON decision protocol; implement a serial LangGraph;
add durable SQLite checkpoints with operation receipts and conservative recovery;
validate and switch defaults while retaining custom for one release cycle.
Langfuse is deferred: no SDK, deployment, credentials or remote export in this work.

## Baseline preservation

`scripts/freeze_refactor_baseline.py` saved and hash-verified 231 working-tree files
in `runs/pre-langgraph-baseline/source.zip`, with a per-file manifest and Python
runtime information. This includes previously uncommitted source and tests.
It is not yet proof of a fully restored release environment.

The prior analysis-only focused suite passed 122 tests. A fresh full baseline
suite is running with output in `runs/pre-langgraph-baseline/pytest.txt` and JUnit
in `runs/pre-langgraph-baseline/unit.xml`. Inspect the actual command completion
before treating these artifacts as a passing baseline.

Wheel build succeeded using workspace-local `runs/uv-cache` after authorized
dependency retrieval. The wheel is in `runs/pre-langgraph-baseline/wheel/`.
The source archive was extracted to `runs/pre-langgraph-baseline/restored/` and
`uv sync --frozen` successfully installed all 32 dependencies into its own venv.
ShopFlow baseline passed 67 tests (see `shopflow-tests.txt`). Full DevPilot
regression and benchmark validation are still running; do not change runtime
source until baseline execution has finished.

Active command handles at this checkpoint: full pytest 1619; benchmark 95578;
restored CLI help plus snapshot-script lint 45917. Poll these exact handles before
restarting anything. Full pytest output is buffered at 13 percent; its process
was confirmed live with CPU activity, not assumed stuck from the log alone.

## Outstanding acceptance gates

- P0: full regression; benchmark self-check; wheel build/install; reproducible old
  environment; Windows/Linux evidence and compatible framework dependency lock.
- P1: shared application factory, public outcome construction, neutral shared
  services and isolated sessions with old import compatibility.
- P2: shared parser, LangChain adapter, provider fixtures and no hidden retries.
- P3: serial graph, explicit failure/finalization, dual-runtime contract tests.
- P4: SQLite, receipts, precharged requests, identity checks, locking, quota
  accounting, fault injection and correlated local trace events.
- P5: full matrix, ten paired overhead measurements, default switch, rollback
  exercise and accurate documentation.

Do not restore old checkpoints using a modified package: the existing recovery
fingerprint hashes all package Python files. Preserve the old distribution.

## Framework feasibility evidence

The isolated `runs/framework-probe` environment resolved LangGraph 1.2.18,
LangChain Core 1.7.1, LangChain OpenAI 1.7.3 and SQLite checkpointer 3.1.2.
`scripts/probe_framework_runtime.py` passed async graph execution with synchronous
durability, SQLite connection close/reopen state retrieval, and JSON model binding
with retries disabled. It made zero model requests. Evidence: framework-probe's
`result.json` and `uv.lock`. Main project dependencies remain unchanged.
The restored old CLI help and both new scripts' lint checks passed.
Benchmark has reported PASS for DEV-001 through DEV-006; full completion remains
unverified. Full baseline pytest handle 1619 and benchmark handle 95578 remain
the processes to inspect next.

## P1 entrypoint and shared service changes

Benchmark handle 95578 completed successfully: all eight tasks PASS.
CLI run/resume and EvalRunner now construct RuntimePort through
`application.factory.create_runtime`; old bootstrap exports remain available.
CLI/settings/framework-independence regression passed 43 tests. A new public-port
test passed for run/resume using an object with no concrete runner properties.
Decision/ToolExecution/Acceptance services and RunSession moved into runtime/shared;
old paths re-export the same classes. Targeted lint passed.

Boundary/smoke regression is active as handle 93596 with output in
`runs/p1-shared-tests.txt`. The early full-suite handle 1619 is still running,
but source changed during execution: its result must NOT be presented as an
immutable pre-migration baseline. Revalidate the frozen source and final source
separately before release. The source archive and wheel remain unchanged.
P1 remains incomplete: outcome ownership and neutral context/state/guards still
need extraction, followed by P2–P5 implementation and acceptance.

ContextBuilder, StateManager and LoopGuard now live under runtime/shared with
explicit compatibility exports from custom. Custom runner owns RunOutcome
construction through run_outcome/resume_outcome; the application adapter no longer
reads runner metrics/verifier/budget internals. Workspace assembly still needs
cleanup. The shared decision parser is extracted; 19 LLM/agent tests passed.

Boundary regression 93596 finished with 21 passed and one timer assertion failure:
evaluation terminated correctly after two calls but measured 2.999 seconds against
a strict 3-second lower bound on Windows. The assertion now permits 50 ms scheduling
granularity while retaining the two-call, termination and upper-bound checks.
Its focused rerun is active (see latest command handle). Broader neutral-service
tests are active as 18601; inspect results before accepting this change.

## P2 model adapter implementation

The focused timer rerun passed. Neutral shared-service regression completed:
110 passed. Model protocol construction (schema hint, tools and context bound)
is now shared by OpenAIClient and LangChainLLMClient. The new adapter uses
ChatOpenAI with retries disabled, Chat Completions explicitly selected, local-only
tracing, original JSON parsing, and nullable usage/error records. Fake takes
precedence over backend selection. Settings and run/eval now accept llm_backend.
Defaults remain custom/OpenAI pending all release gates.

Framework dependencies were added to pyproject and uv.lock; main venv is not yet
synced because old full-suite handle 1619 is still active. Independent model tests
passed 35 cases in the probe venv, including parse-error billed usage, cancellation,
no retry, missing usage and no dispatch on oversized context. That probe venv has
some newer dependencies than the project lock; repeat on the frozen project env
before release. Transport-level provider fixtures and expanded network guards
remain outstanding, as do P1 workspace assembly and P3–P5.

## Frozen environment follow-up (2026-10-30)

The early full suite finished with 531 passed and 2 skipped in 1473.63 seconds.
Because source changed while it was running, this is interim evidence only.
Main venv has now been synced with `uv sync --frozen`. The CLI enum/Annotated
options lint issues are fixed. Bootstrap accepts RunRequest and owns workspace
selection/purpose/policy; CustomRuntime no longer patches assembled runner fields.
LangChain now reserves the same schema-hint context length as OpenAIClient.
Frozen-environment model/CLI/settings/eval/boundary regression was started with
output in `runs/p2-frozen-tests.txt`; inspect completion before accepting P2.

## P3 topology implementation started

Added runtime/langgraph/graph.py with explicit serial prepare/guard/context/decide,
plan/tool/observation, verify, fail and finalize routing. Node services are injected;
no existing custom loop is hidden inside a graph node. Framework interrupts and
cancellation propagate; ordinary node failures route to fail. Finalization errors
propagate to the future outer lifecycle handler. This is topology only, NOT a
functional replacement runtime yet: concrete nodes, persisted state, request
ledger/receipts, lifecycle adapter and factory selection remain to implement.
Topology test handle 47082 validates actual graph execution with synthetic node
services. The frozen model regression handle 7444 was confirmed still live; keep
polling rather than starting a duplicate solely due to absent buffered output.

## Shared execution step extraction

Topology tests finished: 2 passed, lint clean. Added shared/steps.py and made
CustomAgentRunner call shared decide, tool dispatch, observation, plan-feedback
and verification steps. Existing budget, guard, tracing, resource admission and
result behavior remains in these shared implementations. Verification/observation
still finalize terminal results internally; separating terminal projection from
graph progression remains necessary before wiring real graph nodes.
The first extraction test command had an incorrect planning-test path and exited
without tests; it was corrected (handle 22270, p3-step-extraction.txt).
A new regression for the subsequent observe/verify extraction is running with
output p3-observe-verify-tests.txt. Do not treat older tests as verification of
the later extraction. Runtime factory still selects custom only.

## P3 real graph runner wired (partial)

Added LangGraphAgentRunner and Settings.runtime selection (default custom).
Bootstrap selects the graph runner for runtime=langgraph. The locked lifecycle
dispatches `_execute_loop`, which the graph implementation replaces entirely;
it never invokes the custom while loop. Real model/tool/observe/plan/verify nodes
call shared execution steps. Smoke contract verification is active as handle
18598, output runs/p3-graph-smoke.txt. Observe/verify extraction regression passed
17 tests before this graph wiring.

This is an in-process serial milestone only. Graph runner currently inherits
custom lifecycle helpers and keeps ephemeral node data in a per-run closure;
state must become checkpoint-authoritative during P4. Terminal persistence is
still performed by shared verify/observe helpers. Runtime checkpoint markers now
distinguish graph from custom, and graph resume is explicitly refused until P4;
custom refuses graph checkpoints. Remaining P3 work includes max-step verdict
equivalence, failure/plan/retry contract matrix, CLI runtime flag and lifecycle
neutralization. P4/P5 and final immutable-source verification remain required.

## P3 lifecycle neutralization and CLI

Real graph smoke/topology/custom-smoke run completed: 5 passed. Moved run locking,
preparation, recovery checks, outcomes, diagnostics and checkpoints into shared
RuntimeLifecycle, and recovery models into shared/recovery. Custom runner now
only supplies the while-loop scheduler; graph runner independently derives from
the common lifecycle. Legacy recovery exports and uuid/tempfile aliases remain.
The snapshot-failure test now patches the implementation in shared/lifecycle.

CLI run/eval support --runtime custom|langgraph. Both implementations use the
same max_steps_step terminal projection, avoiding a graph guard exception changing
the old max-step verdict. Lifecycle/recovery regression is active as 9761 with
p3-lifecycle-tests.txt. Graph smoke and paired max_steps/max_llm_requests cases
are active as 27158 with p3-budget-equivalence.txt. P4 durable graph state and
operation receipts are not yet implemented; defaults have not switched.

## P4 state and SQLite groundwork

Lifecycle regression passed 39 tests; paired graph smoke/budget tests passed 3.
Graph messages, decision, feedback and tool results now travel in serializable
GraphState, with per-node budget/request/guard/metric accounting snapshots.
Nodes validate a copy of domain state before mutation. The first projection run
exposed lost domain updates on a failing observe node (max-step verdict had zero
instead of one step); returning the updated domain along the failure edge fixed
it. Corrected comparison passed 3 tests (p4-failure-state-tests.txt).

Added QuotaSqliteSaver with serialized async admissions, write-growth reservations,
and post-write capacity checks; graph.sqlite lives inside each run artifact folder.
Graph execution uses thread_id=run_id and sync durability. Persistence failure
after verifier success forces a failed outcome. SQLite smoke/budget test handle
69740 writes p4-sqlite-smoke.txt. The smoke test additionally reopens SQLite and
checks persisted domain, request accounting and final result; rerun if this
assertion was added after the running process collected tests.

Graph resume remains explicitly refused. Receipt journaling, crash-window budget
reconciliation, checkpoint authority, recovery manifests, trace de-duplication,
fault injection and P5 remain outstanding. SQLite alone is not safe replay.

## P4 tool receipts integrated

SQLite smoke/budget run completed: 3 passed in 56.71s. After receipt integration,
tests/runtime/test_graph_runner.py passed 3 tests in 66.00s; this run includes
closing/reopening SQLite and checking final persisted domain, request count and
result (runs/p4-tool-receipts-smoke.txt).

OperationJournal now persists prepared/completed tool receipts through the
existing atomic, quota-admitted artifact writer. Stable decision IDs use the
run ID and charged request count. Execution fingerprints both workspace and
trusted snapshot before and after the operation. A completed matching receipt
can supply its prior result; prepared receipts, changed parameters or files,
missing results and redacted/modified result payloads refuse automatic replay.
Five focused journal tests passed, including failed completion writes. Ruff passed.

This is tool receipt groundwork, not enabled recovery: model request ledger,
verification receipts, accounting restoration, authoritative graph resume,
deduplicated trace events and broader crash-injection tests remain incomplete.
The previous turn was progress (failure-state correction plus SQLite integration);
this turn adds verified tool receipts. Defaults remain custom/OpenAI, Langfuse deferred.

## P4 model request ledger

Graph model attempts now use the same atomic receipt writer. Before dispatch,
each attempt saves its charged request count, turn attempt and cumulative budget
snapshot under a stable run/model/request ID. Message contents are fingerprinted,
not copied into the admission record. Completion stores the parsed decision (if
available), provider usage record (nullable), metrics and budget snapshot.
Admission and completion storage failures bypass the model retry loop. Admission
precedes the legacy JSON checkpoint, so a checkpoint failure cannot leave an
unrecorded provider call. Cancellation preserves charge and unknown usage.

Initial graph smoke/budget tests passed 3 in 67.68s. The first ledger harness had
an invalid boolean FinishIntent fixture, corrected to the actual domain schema.
The combined run then passed 17 tests; two additional fault-window tests and an
admission-order correction were verified by 5 ledger tests (5.20s). Ruff passed.
Final fixed-source combined rerun is session 82134, writing
runs/p4-model-ledger-verified.txt; inspect its terminal output before claiming the
full final group passed.

Final fixed-source run 82134 subsequently exited successfully; see the verified
log for its exact test count and timing. This covers ledger fault windows, tool
receipts, existing request-budget cases, and graph smoke/budget equivalence.

Graph resume is still disabled. Reconciliation must select graph state as the
domain authority, apply newer request receipts without double-charging, preserve
original wall-clock deadlines and cumulative evaluation use, and reject prepared
side effects. It must also restore guard/metric state and validate runtime identity
and workspace/trusted inventories. Current legacy resume accepts only ready and
llm_inflight JSON stages, so simply enabling its inherited path would be wrong.

## P4 verification receipts

The prior goal turn made progress: model ledger implementation and fixed-source
19-test regression passed in 74.33s. This turn extracts a shared verifier invocation
hook and gives the graph a durable verification receipt, written before business
state transitions and terminal artifact publication. Receipt admission records
the budget and workspace/trusted fingerprints. Completion records the verifier
report, evidence projection, evidence-directory fingerprint and cumulative budget.
Reuse checks both workspace/trusted and evidence fingerprints, restores evidence,
and takes the maximum evaluation charge without extending the original deadline.
Prepared/uncertain verification is never automatically repeated.

Three focused verifier receipt tests passed in 12.98s; real graph smoke and
custom/graph budget equivalence passed 3 in 134.87s
(runs/p4-verification-receipts-smoke.txt, completed session 68866). Ruff passed.

Remaining P4 work includes authoritative graph resume/reconciliation and deferring
terminal publication until the graph checkpoint succeeds. The shared verify step
still publishes terminal artifacts before the enclosing graph completes; receipts
close the verifier-result window but do not by themselves solve that later window.
Default switching and P5 remain outstanding; Langfuse stays deferred.

## P4 terminal publication after graph durability

Previous turn was progress: verifier receipts and their integration tests passed.
Graph execution now keeps terminal results in graph state and queues terminal
events/traces until synchronous graph checkpoint writes and saver closure succeed.
Only then does it save final artifacts and publish terminal notifications. If final
artifact persistence changes a successful result to failed, queued success events
are replaced by failure notification. A graph write exception drops queued success
events and flows through the shared failed-outcome path after clearing graph mode.

Two publication unit tests passed in 27.96s (success and artifact-write failure).
Real graph tests passed 4 in 327.48s, including a late SQLite write failure injected
after verification and assertions that result.json and completion notifications
are absent during terminal checkpoint writes. Existing graph/custom budget cases
also passed. Evidence: runs/p4-terminal-publication.txt; session 81808 exited 0.
Ruff passed. Tests were slow but live and completed; no restart was necessary.

Graph-authoritative resume, request/accounting reconciliation, trace deduplication,
recovery routing/manifests and comprehensive P5 validation remain incomplete.
Crash recovery after graph completion but before result publication must recreate
publication from saved graph state; the live deferred event lists are not durable.
Default engine remains custom and Langfuse remains deferred.

## P4 coherent graph recovery metadata

The previous turn was progress (deferred terminal publication with four passing
integration tests). Graph snapshots now include a versioned recovery channel:
run/runtime identity, configuration, purpose, preparation duration, original budget
start/deadline, and workspace/trusted inventories. Inventories refresh after tool
and verification operations; other nodes preserve the same inventory. The budget
service start time is used consistently because the legacy lifecycle start timestamp
can differ from it by milliseconds.

Added checkpoint_from_graph to project a single graph snapshot into the shared
session contract without reading legacy JSON state. It rejects mismatched IDs,
runtime/config identities, budget origin or schema, and retains request/attempt
counts, evaluation charge, remaining time, guard and metrics state.

Verification is pending: session 81057 runs the recovery projection unit tests and
ruff; session 20134 runs the real graph success case with SQLite reopen/projection
assertions, writing runs/p4-graph-recovery-projection.txt. Both handles were confirmed
running without output. Earlier ruff for the new runtime module passed (31634).
Do not claim these pending tests passed. Resume stays disabled until coherent
state restoration, operation/request reconciliation and crash tests are completed.

Projection unit run 81057 finished with 10 fixture setup errors: StateManager
requires RuntimeConfig. The fixture was corrected; rerun is session 20478.
Ruff completed successfully. Real graph run 20134 remains pending. These errors
did not exercise the recovery assertions and are not evidence of passing behavior.

Corrected projection unit run 20478 subsequently passed all 10 tests in 19.15s.
Real graph projection/reopen run 20134 is still running and must be checked next.

## P4 graph resume and request reconciliation

Run 20134 completed successfully: real graph projection/reopen test passed in
213.97s. Model receipt reconciliation now restores charged attempts, metrics and
budget, reuses recorded decisions, preserves unknown interrupted usage, and never
extends the deadline. Initial reconciliation fixture omitted lifecycle fields;
after correction its 10-test ledger/reconciliation group passed in 6.79s.

Graph resume now holds the OS run lock, reads a graph snapshot using its checkpointer,
validates graph metadata and runtime identity, and resumes with graph input None.
Workspace changes require a completed receipt for the pending tool/verifier;
uncertain effects are refused. New service instances restore metrics/guard/budget.
Checkpoint validation evidence is now persisted/restored too, so a graph completed
before publication can publish without rerunning verification or losing evidence.

Fresh-instance crash tests passed 3 in 25.20s; expanded graph recovery/projection/
model reconciliation group passed 19 in 27.97s (runs/p4-resume-verified.txt).
Independent Python process recovery plus legacy custom recovery regression is
running as session 3053, output runs/p4-cross-process-resume.txt. A test assertion
was accidentally moved outside its original test during addition; it was corrected
and ruff now passes, but rerun the subprocess case if the running suite collected
the prior test body. No cross-process success claim until that result is inspected.

Still outstanding: complete unknown-usage accounting when a completed request
receipt has no provider record, trace deduplication, manifest/version routing,
broader crash/process-death coverage and P5/default switch. Resume implementation
is present now; full recovery correctness is not yet established by these tests.

Session 3053 completed with 31 passed and one test-body NameError after the
subprocess had returned the expected successful recovery result. The stray
assertion was already corrected. Completed model attempts without provider records
now explicitly add an unknown-usage metric before saving their receipt; regression
coverage verifies that reconciliation retains unknown total usage. Final fixed-source
graph-resume/model-ledger/reconciliation run is session 16294, writing
runs/p4-resume-final.txt. Ruff passed. Original custom recovery tests were included
in the 31 passing cases before this last graph-only accounting correction.

Final run 16294 exited 0: all 16 tests passed in 36.37s. This includes resuming in
an independent Python process with zero new model calls, receipt reuse/refusal,
completed-graph evidence publication, and unknown-usage accounting. Initial loss
is simulated with an uncaught BaseException; OS-kill timing/fault coverage is still
outstanding, as are recovery routing/manifests, trace deduplication and P5 gates.

## P4 versioned run manifests and routing

The prior turn made verified progress: 16 graph recovery/ledger tests passed,
including fresh-process reuse. New runs now persist run-manifest.json before model
dispatch, identifying the runtime, model adapter and relevant installed dependency
versions without credentials. Application resume selects those recorded backends
without mutating current Settings. Both runners revalidate the manifest under the
run lock before restoring state. Unknown custom adapters require their original
factory. Existing checkpoints without manifests still follow the caller settings;
legacy routing during the future default switch needs an explicit compatibility gate.

Inspect displays manifests when present and preserves legacy inspect directories
without manifests (including older nonstandard names). Initial routing, graph resume
and entrypoint group passed 11 tests in 40.37s (p4-manifest-routing.txt). Expanded
real-bootstrap routing, CLI and settings regression is session 92120, output
runs/p4-manifest-cli.txt. Check its result before claiming completion of that group.
Ruff initially fixed import ordering; prior focused lint passed.

Trace deduplication, true process termination windows, legacy/default routing policy,
full P5 comparison/performance/packaging gates and default switching remain open.

Expanded session 92120 exited 0: 29 manifest/bootstrap/CLI/settings tests passed in
44.63s. This establishes current routing and inspect compatibility; it does not
establish migration of unversioned checkpoints under a future changed default.

## P4 logical trace identity and replay deduplication

Previous turn made verified progress on manifests/routing. Graph checkpoints now
carry a node execution sequence; context-local trace scopes derive stable IDs from
run/node/sequence, event name and occurrence. Model request events instead use the
charged request number so a genuinely new retry cannot collide with a prior attempt
when the decision node is replayed. Lifecycle terminal/start events also have stable
identities. Legacy unscoped writers retain append behavior.

Identified events commit atomically with their IDs in trace.jsonl, admitted through
the existing artifact quota policy. There is no separately committed dedup index.
Reopened writers skip an existing ID; malformed/incomplete previous records fail
closed without deleting data. Atomic full-file replacement adds I/O and temporary
capacity costs which must be included in the P5 performance gate.

Trace/terminal/recovery group passed 39 tests in 39.22s. Real observation replay
after a crash before graph checkpoint publication plus real graph smoke passed 2
in 50.60s (runs/p4-trace-replay.txt). The replay test verifies one tool_result,
one run_started, one run_completed and unique nonempty event IDs across fresh
writer instances. Focused new model-attempt identity regression is running as
session 29271 with the identity tests. Ruff fixed import order; no product code
changes followed the real replay regression.

Remaining gates include actual OS termination, unversioned/default routing policy,
broader graph/custom contracts, transport isolation, benchmark/performance evidence,
packaging and the final default switch. Langfuse remains deferred.

Focused identity run 29271 completed: 5 passed in 5.47s, including preservation of
distinct model retries while repeated emission of the same request is deduplicated.

## P4 operating-system process termination coverage

Previous turn made verified progress on trace identity. Added a dedicated fake-only
worker process that signals an exact durable boundary and then waits for the parent
to terminate it. Tests use Process.kill on the owned child, wait for confirmed exit,
and resume using a separate Python process. They verify the live child holds the
run lock and that the kernel releases it after termination.

Initial six-window run passed 6 tests in 99.91s (runs/p4-process-kill.txt): completed
model receipt, completed/prepared tool receipt, completed/prepared verification
receipt, and completed graph before terminal publication. Completed effects resume;
uncertain side effects refuse automatic replay. Workspace contents are checked.

Expanded fixed-test run 25825 is running all seven windows, adding model completion
before its result receipt (unknown usage and preserved charge), plus unique nonempty
trace IDs after every recovery. Output: runs/p4-process-kill-final.txt. Ruff passed.
This is local Windows OS-termination evidence, not Linux or remote-provider evidence.
No production code changed in this turn. P5/full matrix, old-checkpoint routing,
provider transport fixtures, performance and default switch are still outstanding.

Expanded seven-window run 25825 completed successfully: 7 passed in 114.01s.
The additional model window preserves two charged attempts with one new provider
stub call and unknown usage for the interrupted attempt. All recovered trace IDs
remain unique. Evidence is in runs/p4-process-kill-final.txt.

## P2 actual SDK transport verification

Actual ChatOpenAI and OpenAI SDK calls now run against httpx.MockTransport fixtures.
Tests validate request path, complete prepared messages/tool descriptions, JSON
response format, token limit and temperature, unknown usage, billed parse failures,
429/500 responses, timeout and cancellation with no implicit retries. Global test
guards also block httpx network transports and requests-based tracing; fixtures
enable LangSmith environment flags and assert no real network attempt occurs.

Wire inspection exposed ChatOpenAI renaming max_tokens to max_completion_tokens.
The adapter now supplies max_tokens through extra_body to preserve the established
provider-compatible request. Strict cancellation testing exposed the installed
framework masking an inner CancelledError as AttributeError during result aggregation.
A request-local callback retains cancellation so the adapter preserves CancelledError
and records it correctly, without enabling remote callbacks/tracing.

Initial tests passed 29; stricter cancellation run failed 1 of 40. After the fix,
40 passed in 26.21s (runs/p2-sdk-cancellation-fixed.txt). The previous process handle
72645 is no longer available; the completed output is the evidence. Added caller-
initiated cancellation while the mock transport is awaiting a response. Final
41-test group is session 6082, output runs/p2-sdk-final.txt. Ruff passed.
No real provider credentials, paid requests or remote exports were used.

Final transport/cancellation/budget group passed 41 tests in 24.81s. Full current
DevPilot regression has started as session 83836, writing runs/p5-full-regression.txt
and runs/p5-full-regression.xml. Keep production source unchanged until it completes;
poll this handle rather than launching a duplicate suite. Passing focused tests do
not yet prove the full P5 gate, performance budget, platform matrix or default switch.

## P5 regression monitoring and overhead harness

Full regression session 83836 remains confirmed running; buffered output currently
shows 11 percent with no reported failure. No duplicate suite was launched and no
production source changed during this turn. Prior turn was progress (transport
fixes and the passing 41-test group); this turn adds the measurement harness while
continuing verified waits on the existing regression.

scripts/compare_runtime_overhead.py prepares at least ten paired offline runs with
alternating backend order, fresh subprocesses and isolated artifact directories.
It verifies outcome/request/step/observation/diff equivalence and records execution
time, whole-process time and artifact bytes. It reports median overhead without
declaring an acceptance threshold passed. Execution timing excludes imports and
uses the fake model, explicitly limiting the measurement scope. Help and ruff pass;
the benchmark itself has NOT run and must wait for the regression to finish to
avoid concurrent-load distortion. Output defaults to runs/p5-overhead and refuses
to overwrite an existing measurement directory.

## P5 archived environment recovery evidence

Previous turn made progress by documenting acceptance gaps and confirming live
regression activity. Current full regression 83836 remains running; no restart or
production edits occurred. Archive SHA-256 and all 231 archived file hashes were
revalidated, and every corresponding restored file matches the original manifest.
Evidence: runs/p5-baseline-integrity.json (zero restored mismatches).

The restored environment's own .venv Python imports devpilot from the archived
restored source, not the current workspace package. Its selected original recovery
test passed in 24.04s (runs/p5-archived-recovery.txt, session 18120). That test creates
an interrupted checkpoint using archived code and resumes it in that same preserved
environment while checking workspace content, steps, request budget, guard state,
unknown usage and terminal checkpoint. This proves that specific archived recovery
path, not migration of arbitrary historical checkpoints into the new package.

Final-wheel clean installation, comprehensive rollback, whole-project baseline
coverage outside the 231 selected files, Linux evidence and changed-default legacy
routing remain separate gates. Do not overstate this focused archived test as full
P0/P5 completion.

## P5 candidate wheel installation

Production source remains frozen for regression 83836. Existing CI already has
Windows/Linux jobs and invokes scripts/check_wheel.py. Extended that script to
execute both custom and graph fake smoke contracts outside the source tree, checking
packaged resources, seven steps/eight requests, manifests and graph.sqlite.
It now accepts an explicit wheel path and rejects ambiguous wheel selection.

Candidate wheel built offline at runs/p5-wheel-candidate/devpilot-0.1.0-py3-none-any.whl.
Initial installation failed because broad package resolution selected uncached
versions. Installation now uses requirements exported from uv.lock with --frozen.
The locked offline attempt also found missing cached distributions; added explicit
--allow-download for fetching those exact versions. Authorized download/install/
dual-runtime validation is running as session 17283, log runs/p5-wheel-install-online.txt.
Do not claim wheel installation passed before inspecting its terminal result.
Default offline behavior remains for CI with a populated cache. This is a candidate
wheel, not final release validation after the planned default switch.

## P5 shared business assertions for graph

Previous turn made progress on the wheel verifier and candidate build. Sessions
17283 (installed wheel) and 83836 (full regression) are still confirmed live;
full regression output has reached 47 percent without a reported failure.

Added tests/runtime/test_graph_business_contracts.py, reusing the original custom
repair/self-correction/planning test classes and replacing only their runner factory
with LangGraphAgentRunner. Original modules retain custom coverage. The additional
matrix covers repair success, plan-update loop termination, duplicate actions,
retry limits, verifier rejection, trace/metrics artifacts, no-verifier compatibility,
plan context, verification hints and plan updates during repair.

Ruff passed and collection found 16 tests (90632 exited 0). They have NOT executed;
the currently running full suite collected before this module existed. Run this
module after the active suites finish and include it in the final full regression.
Production source remained unchanged. No performance samples were run under load.

## P5 completed full regression and installed-wheel checks

On resumption, handles 83836 and 17283 were no longer present. Their completed logs
provide terminal results: full regression passed 607 tests with 2 skips in 1953.78s;
JUnit confirms 609 cases, zero failures and zero errors. Both skips concern symlink
support unavailable on this Windows environment. The wheel log ends with successful
CLI/resource/both-runtime verification, after clean temporary-environment installation.

Candidate wheel SHA-256 is 15a36c03ac2ef95cf9e4d1d4524510df680fa4966c4b52e207f798a556bc7b7a.
All 151 packaged Python files match current source bytes; no source drift was found
(runs/p5-wheel-source-integrity.json). These facts do not cover future default changes.

The 16 collected business-contract tests now run as session 30057, with output
runs/p5-graph-business-contracts.txt. One inherited duplicate-action case directly
tests the shared guard rather than executing a graph; do not count it as an additional
end-to-end graph case. No duplicate full-suite process was started. Performance
measurements remain deferred until this focused suite completes.

## Migration usage documentation during business-contract validation

Session 30057 was revalidated as live; pytest-138 directories continue advancing.
No duplicate matrix or performance run was started. Added runtime-usage.md with
current backend selection, fake precedence, manifest routing, graph artifacts,
budget-preserving recovery, refusal conditions and explicit custom fallback.
Commands were checked against CLI option declarations. The guide explicitly states
that unversioned-checkpoint routing and default switching remain incomplete and
does not present archived-environment recovery as cross-engine checkpoint migration.
Production source remains unchanged while contract assertions execute.

## Legacy routing regression preparation

Read-only review confirms application resume falls back to current Settings when
run-manifest.json is absent. Added two targeted regressions for the forthcoming
default change: a validated old custom checkpoint must select custom/OpenAI despite
new defaults, and an unidentified graph database without a manifest must be refused
before constructing a model. Current code is expected not to satisfy these tests.
Their pre-fix run is session 51167, output runs/p5-legacy-routing-before.txt; inspect
the outcome rather than claiming they pass. The long business-contract run 30057
remains live, so production routing code has not yet been changed. This preserves
the fixed-source evidence from that run. These tests are new work beyond the prior
607-pass full regression and must be included in the later final suite.

## Business matrix passed; legacy route fixed; performance started

Session 30057 completed with 16 passed in 479.21s. The two legacy-routing regression
cases failed on the previous implementation as expected (51167). After that fixed-
source business run finished, added validated legacy custom-checkpoint routing to
custom/OpenAI; ambiguous graph databases without manifests are rejected. Schema,
run IDs and budget semantics are checked before backend construction; the selected
runner still performs its locked original environment/provider/inventory checks.
No checkpoint conversion or identity bypass was added.

The corrected routing/manifest/entrypoint group passed 9 tests in 9.72s (96316,
runs/p5-legacy-routing-fixed.txt). Ruff passed. User usage guidance now reflects
the implemented legacy policy. These production changes postdate the candidate
wheel and earlier full suite; both must be revalidated for the final release.

With those suites terminal, started scripts/compare_runtime_overhead.py for ten
alternating pairs. Output is runs/p5-overhead-command.txt and samples under
runs/p5-overhead. Keep production source fixed and avoid other heavy test/build
processes until measurement completes. No performance acceptance claim yet.

## First overhead sample recorded

Session 69532 remains live and has recorded the first custom sample: completed,
7 steps, 8 requests, 65.2301s measured execution, 73.2614s including process/import
startup, and 80,359 artifact bytes. This is one sample only, not a paired comparison
or median. Production source stayed unchanged and no concurrent tests/builds were
started. The available acceptance records specify ten pairs but do not establish
a numerical overhead threshold; report measurements and tradeoffs explicitly rather
than inventing a threshold or treating successful script execution as performance
acceptance. Continue polling 69532 and preserve its existing samples.

## First pair verified; descriptive analysis prepared

First pair completed with matching business contracts. Graph execution was
95.6666s versus custom 65.2301s. Graph artifacts totaled 1,460,706 bytes, of which
graph.sqlite was 1,347,584 bytes. These are single-pair observations only; they do
not establish median overhead or performance acceptance. Session 69532 remains live.

Added summarize_runtime_overhead.py to validate at least ten complete unique pairs
and matching completed outcomes, then report median/min/max paired overhead,
absolute extra time and artifact ratio without modifying raw samples. Ruff and
synthetic arithmetic/incomplete/duplicate rejection checks passed. It has not yet
analyzed a complete measured dataset. The sampling script and production source
remain unchanged; no heavy concurrent test or build was started.

## Acceptance checklist corrected; clean-CI wheel downloads explicit

On 2026-11-03, write_stdin revalidated performance session 69532 as live;
the command log had five completed pairs. The full dataset is not yet available.
Updated remaining-gates.md to reflect the completed business-contract and legacy
routing checks, the terminal earlier full regression, and the actual active
performance handle. No production or sampling source was changed.

The CI wheel verification now passes --allow-download explicitly. check_wheel.py
still exports frozen locked requirements and installs those exact requirements;
its local default remains offline. This removes reliance on a clean CI runner
already having every wheel-verification dependency cached. Parsed the workflow
with PyYAML, asserted the flag and both OS matrix entries, and passed git diff
--check. This is configuration validation, not evidence of a completed CI job.

## Evaluation and timeout matrix expanded, execution pending

Read-only coverage review found that the five trusted-hidden-evidence verdict
cases in test_eval_truthfulness.py and the preparation/cumulative-verification
timeout cases in test_p0_p2_boundaries.py selected only custom. Parameterized
these existing assertions over custom and langgraph: evaluator cases select the
backend through Settings; timeout cases substitute the runner at the existing
test helper's construction boundary. No success criterion or timing tolerance
was weakened. This adds seven graph cases while retaining the custom cases.

Ruff and git diff --check passed for the two files. Runtime assertions have NOT
executed yet: performance session 69532 was revalidated live and its log reached
six completed pairs. Run the expanded focused matrix after sampling completes,
then include it in the final full suite. Production and sampling code stayed fixed.

## Real resume dependency-drift regression prepared

Added test_dependency_drift_refuses_real_resume_before_dispatch to
test_graph_resume.py. It creates an interrupted graph run with real persisted
state, changes the recorded LangGraph dependency version, and requires the real
resume entrypoint to refuse before model dispatch while preserving run artifact
bytes. This supplements the existing mocked manifest comparison test. Ruff and
diff checks passed; runtime execution remains pending until the performance run
ends. Session 69532 was revalidated live twice, with six pairs reported at the
latest log read. No production changes or competing heavy processes were started.

## Ten-pair sampling complete; application naming cleaned; final matrix running

Session 69532 exited 0 after all ten alternating pairs. The standalone analyzer
validated complete unique pairs and matching completed contracts. Raw samples
remain under runs/p5-overhead; descriptive analysis is runs/p5-overhead-analysis.json.
Execution medians: custom 65.6966s, graph 84.8875s (ratio of medians +29.21%).
Median paired overhead is +37.00%, range -35.96% to +352.97%; median paired extra
time is 19.3420s and median artifact ratio 18.1776. These different statistics
must not be conflated. Large variation and the Fake/local-I/O workload limit
generalization; no acceptance threshold was inferred from successful execution.

After sampling ended, renamed the shared application adapter ApplicationRuntime,
retaining CustomRuntime as a compatibility alias; factory uses the neutral name,
and bootstrap now annotates the shared RuntimeLifecycle return type. Ruff and
git diff --check passed. No change to default backends or execution semantics.

Started the expanded evaluator/timeout/dependency-drift/entrypoint/manifest/legacy
matrix as session 71178, output runs/p5-final-matrix.txt. This includes the newly
prepared graph assertions and application naming changes. Results are pending;
preserve source until this run completes. Final full regression and rebuilt wheel
remain outstanding, as do supported-platform and performance acceptance decisions.

## Scoped performance decision recorded

Added performance-decision.md with the complete measured statistics, methodology,
large variance, and explicit limits. Accepted the persistence cost for the current
local serial task workflow as an engineering tradeoff, not a fabricated numerical
gate: graph median artifacts are 1,460,696.5 bytes and every graph SQLite file is
1,347,584 bytes. Maximum measured graph execution is 158.793s. These fit this
workload's configured budgets but do not prove capacity for longer/concurrent runs.
No durability guarantee was weakened. Updated the checklist and usage guide.

The expanded matrix session 71178 remains live on direct polling, with buffered
output not yet reporting a terminal result. No duplicate test process was started
and production source was preserved. Final defaults and release gates remain open.

## Expanded focused matrix passed; fixed-source full suite started

Session 71178 exited 0: 26 passed in 502.37s, recorded in runs/p5-final-matrix.txt.
This verifies both runtime variants of trusted-evidence evaluation and preparation/
cumulative verification timeouts, real graph dependency-drift refusal with unchanged
artifacts, application entrypoints, manifest routing and legacy routing. The neutral
ApplicationRuntime naming and compatibility alias are included in this source.

Updated both READMEs to describe actual explicit backend availability and link the
migration guide; corrected its stale pending-performance statement. Diff checks
passed. Default backends remain custom/OpenAI.

Started the complete current suite as session 17582, logs runs/p5-expanded-full.txt
and JUnit runs/p5-expanded-full.xml. Recorded production/test Python, lock/project
and CI file hashes in runs/p5-expanded-source.json for source-drift verification.
Keep source unchanged while it runs. This full run includes new tests omitted from
the previous 607-pass result; no full-suite completion claim yet.

## Refreshed wheel built; installed recovery verification prepared

Built runs/p5-release-candidate/devpilot-0.1.0-py3-none-any.whl offline from the
fixed current source (build session 19671 exited 0). SHA-256:
a73d84001b395aae3dba42265eaad04df48de61b15566a3f7c8569eb743ac624.
All 151 packaged Python files match source bytes; the 236-file full-suite source
snapshot also remains unchanged. Evidence: runs/p5-release-integrity.json.
This candidate retains custom/OpenAI defaults and must be rebuilt if they change.

Extended check_wheel.py so its installed graph smoke run is interrupted after
durable terminal graph state but before publication, then resumed through a fresh
public application entrypoint with conflicting custom/OpenAI defaults. The run
manifest must route back to graph/Fake and preserve the original seven-step,
eight-request outcome and custom-equivalent diff. No source test helpers are
used. Ruff, diff checks and compilation of the embedded installed-check code
passed. Actual installed recovery execution has NOT run yet; wait for full
regression to finish before adding that workload.

Session 17582 remains live on direct polling, with the buffered log at 11 percent.
No replacement suite was launched and no production or test files were modified.

## User explicitly defers Linux acceptance

On 2026-11-03 the user answered the environment question: no Linux acceptance
environment is available; skip it for now. Linux execution is therefore no longer
a default-switch/release gate for this task. Preserve the existing CI matrix,
report Linux as unverified, and continue Windows regression, installed-wheel
recovery/rollback, default switching and final verification. No system installation
or remote publication is required to satisfy the waived gate.

Session 17582 was again confirmed live. Its pytest directories advanced through
planning scenarios despite a buffered 11-percent log line. The candidate source
remains unchanged; no duplicate suite was launched.

## Expanded full regression verified; installed candidate validation started

On 2026-11-07, session 17582 was absent. Its terminal log reports 633 passed,
2 skipped in 2510.11s; JUnit independently confirms 635 cases, zero failures and
zero errors. All 236 hashes in p5-expanded-source.json still match current files.
This includes the newly added graph business, evaluation, timeout and real
dependency-drift checks, plus application naming and legacy routing fixes.

Started scripts/check_wheel.py against the refreshed candidate in an isolated
environment outside source, using cached locked dependencies. Session 90923 is
live; output is runs/p5-release-install.txt. Installation has completed and actual
runtime/recovery assertions are in progress. Do not infer success from dependency
installation alone. Default switching remains pending this installed validation;
Linux acceptance remains explicitly waived by the user.

## Installed recovery passed; defaults switched and routing verified

Session 90923 exited 0. runs/p5-release-install.txt ends with installed-wheel CLI,
resources, both runtime contracts and graph resume verified. This candidate was
built before switching defaults.

Changed Settings defaults to langgraph/langchain, retaining explicit custom/openai
and manifest-driven historical routing. Updated .env.example and both READMEs plus
the usage guide. Added a no-network bootstrap regression covering default model/
engine selection, explicit legacy fallback and Fake precedence. Ruff passed;
default bootstrap/entrypoint/manifest/legacy group passed 10 tests in 9.73s
(runs/p5-default-routing.txt). No legacy checkpoint schema default was changed.

Started the final default-configured full suite with output runs/p5-default-full.txt
and runs/p5-default-full.xml. Preserve production/test source while it runs. A
fresh wheel with the new defaults and final installed validation are still required.

## Final default wheel built from frozen source

Full-suite session 90018 remains live, with logs at runs/p5-default-full.txt and
JUnit target runs/p5-default-full.xml. Recorded 238 source/test/config/check-script
hashes in runs/p5-default-source.json. Built the default-configured wheel offline
at runs/p5-default-wheel/devpilot-0.1.0-py3-none-any.whl, SHA-256
547d03286b1a72a2e84eaf7f1ac89355265cb4767f98eefc7b4fafa3e4348f94.
All 151 packaged Python files match current source. Evidence is in
runs/p5-default-wheel-integrity.json. Installation/runtime checks for this exact
new wheel remain pending; the previous candidate's success is not substituted.

## Final default full suite passed

On 2026-11-08, session 90018 was absent and its terminal log reports 634 passed,
2 skipped in 2674.63s. JUnit confirms 636 cases, zero failures/errors. Both skips
are Windows symlink capability checks. All 238 hashes in p5-default-source.json
remain unchanged. The new defaults are therefore covered by the complete suite.

Started isolated installation and recovery validation for the exact final wheel
as session 52847, log runs/p5-default-install.txt. Also started final ShopFlow
tests (runs/p5-shopflow-final.txt/xml) and the eight-task benchmark validation
(runs/p5-benchmark-final.txt). These are separate validation environments, with
no performance sampling active. Results remain pending.
