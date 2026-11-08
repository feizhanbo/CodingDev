# Acceptance gates closed

Updated 2026-11-08. P0-P5 is complete for the agreed Windows scope.
See [final-acceptance.md](final-acceptance.md) for requirements and evidence.

- Final full regression: 634 passed, 2 Windows symlink skips.
- ShopFlow: 67 passed. Deterministic benchmark: 8/8 PASS.
- Final installed wheel: CLI/resources, both runtime contracts and graph resume passed.
- All 238 source snapshot hashes and final wheel SHA-256 verified unchanged.
- Defaults: LangGraph/LangChain; custom/OpenAI retained for one compatibility release cycle.
- Ten paired performance measurements passed business equivalence; local-use tradeoff accepted.
- Linux explicitly skipped by user, unverified. Langfuse deferred.

Historical intermediate statuses in implementation-status.md are not current blockers.
