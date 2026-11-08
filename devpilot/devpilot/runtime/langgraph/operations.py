"""Durable operation receipts. Caller must hold the run's exclusive OS lock."""

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class ManualRecoveryRequired(RuntimeError):
    pass


def digest(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    operation_id: str
    identity: str
    stage: Literal["prepared", "completed"]
    before: str
    after: str | None = None
    output: dict[str, Any] | None = None
    output_digest: str | None = None
    admission: dict[str, Any] | None = None


class OperationJournal:
    def __init__(self, sandbox, run_id):
        self.sandbox = sandbox
        self.run_id = run_id

    def _name(self, operation_id):
        return "operations/" + digest(operation_id) + ".json"

    def read(self, operation_id):
        path = Path(self.sandbox.get_runs_dir(self.run_id)) / self._name(operation_id)
        if path.resolve() != path.absolute():
            raise ManualRecoveryRequired("Linked operation receipt refused")
        if not path.exists():
            return None
        receipt = Receipt.model_validate_json(path.read_text(encoding="utf-8"))
        if receipt.operation_id != operation_id:
            raise ManualRecoveryRequired("Operation receipt identity mismatch")
        return receipt

    def begin(self, operation_id, arguments, current_digest, *, admission=None):
        identity = digest(arguments)
        previous = self.read(operation_id)
        if previous is not None:
            if previous.identity != identity:
                raise ManualRecoveryRequired("Operation parameters changed")
            if previous.stage != "completed" or previous.after != current_digest:
                raise ManualRecoveryRequired("manual_recovery_required: uncertain operation")
            if previous.output is None:
                raise ManualRecoveryRequired("Completed operation has no result")
            if digest(previous.output) != previous.output_digest:
                raise ManualRecoveryRequired("Operation result changed or was redacted")
            return previous.output
        self._save(Receipt(
            operation_id=operation_id, identity=identity, stage="prepared", before=current_digest,
            admission=admission,
        ))
        return None

    def complete(self, operation_id, after_digest, output):
        previous = self.read(operation_id)
        if previous is None or previous.stage != "prepared":
            raise ManualRecoveryRequired("Operation was not prepared")
        self._save(previous.model_copy(update={
            "stage": "completed", "after": after_digest, "output": output,
            "output_digest": digest(output),
        }))

    def _save(self, receipt):
        self.sandbox.save_artifact(
            self.run_id, self._name(receipt.operation_id), receipt.model_dump_json(),
        )
