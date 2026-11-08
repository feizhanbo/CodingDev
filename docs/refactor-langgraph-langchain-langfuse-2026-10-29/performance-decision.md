# Performance decision for the local runtime migration

Date: 2026-11-03. Decision: accept the measured persistence cost for the current
local, serial development-task workflow, subject to the remaining correctness,
platform and release gates. This decision does not itself switch the defaults.
It is an engineering tradeoff, not a claim that a previously approved numerical
performance threshold was met; no such threshold was present in the records.

## Evidence

`runs/p5-overhead/samples.json` contains ten alternating-order pairs, each in a
fresh process and isolated run/workspace directory. Session 69532 exited 0.
`runs/p5-overhead/summary.json` and `runs/p5-overhead-analysis.json` retain the
summary and independent pair validation. Both engines completed every run with
matching status, seven steps, eight requests, observation names and diff hash.
No competing heavy tests/builds were launched during sampling. Production and
sampling source remained unchanged until the process exited; application adapter
renaming happened afterward and is not part of this measurement.

| Measurement | Custom | LangGraph |
| --- | ---: | ---: |
| Execution median | 65.697 s | 84.887 s |
| Observed execution range | 35.056–139.770 s | 42.372–158.793 s |
| Median artifact bytes | 80,357 | 1,460,696.5 |
| Maximum artifact bytes | 80,361 | 1,460,727 |

The ratio of execution medians is +29.21%. The median of paired relative
differences is +37.00%, with a -35.96% to +352.97% range. Median paired extra time
is 19.342 s. These are different statistics and must not be substituted for one
another. Median storage ratio is 18.178. Each measured graph.sqlite is 1,347,584
bytes, accounting for most of the additional storage.

## Rationale and limits

The migration seeks explicit orchestration and durable recovery. Local per-run
storage of approximately 1.46 MB and a measured median execution near 85 seconds
are workable for this repository's current interactive, serial development-task
workflow. They fit within the configured 512 MiB per-run artifact limit and
1,800-second task budget for this workload. Those observations do not establish
capacity for larger repositories, longer runs, or concurrent workers.

The measured workload uses a scripted Fake model but real edit/test/verification
operations. Imports are excluded from the execution interval; whole-process time
is separately retained in samples. It does not establish remote model latency,
token cost, throughput, or production tail latency. Ten pairs and large variation
are insufficient to isolate framework overhead or justify a p95 claim. Tool
observation durations also vary between engines; subtracting aggregate medians
would not yield a valid pure checkpoint cost.

Retain synchronous checkpoint durability, operation receipts, budget accounting
and atomic event identity. Do not weaken these guarantees to improve the timing
number. Keep custom/OpenAI available for the compatibility release cycle and
document the observed cost. Continue enforcing disk and wall-clock limits.

For a future larger/concurrent workload, measure that workload separately and
profile checkpoint serialization, artifact inventory scans, SQLite writes and
trace rewrites before choosing optimizations. This local decision grants no
distributed-runtime or long-task performance claim.

## Release implication

The ten-pair measurement and scoped performance decision are complete. Default
switching remains contingent on the expanded regression matrix, final full suite,
Windows platform evidence, rebuilt installed-wheel checks and rollback exercise.
The user explicitly waived Linux acceptance on 2026-11-03 due to the absence of
an available environment. Linux remains unverified rather than a release blocker.
