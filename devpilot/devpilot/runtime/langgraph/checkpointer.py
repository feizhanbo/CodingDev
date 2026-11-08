"""Local SQLite persistence admitted through DevPilot's artifact capacity policy."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


class QuotaSqliteSaver(AsyncSqliteSaver):
    def __init__(self, connection, sandbox, run_id):
        super().__init__(connection)
        self.sandbox = sandbox
        self.run_id = run_id
        self.admission_lock = asyncio.Lock()

    def reservation(self, value):
        # Include database pages and journal/WAL amplification. This is bounded
        # admission, consistent with the project's trusted-local storage model.
        _, payload = self.serde.dumps_typed(value)
        return 65536 + 4 * len(payload)

    async def aput(self, config, checkpoint, metadata, new_versions):
        async with self.admission_lock:
            with self.sandbox.admit_artifacts(
                self.run_id, self.reservation((checkpoint, metadata)),
            ):
                result = await super().aput(config, checkpoint, metadata, new_versions)
            self.sandbox.check_artifacts(self.run_id)
            return result

    async def aput_writes(self, config, writes, task_id, task_path=""):
        async with self.admission_lock:
            with self.sandbox.admit_artifacts(self.run_id, self.reservation(writes)):
                await super().aput_writes(config, writes, task_id, task_path)
            self.sandbox.check_artifacts(self.run_id)


@asynccontextmanager
async def open_checkpointer(sandbox, run_id):
    path = Path(sandbox.get_runs_dir(run_id)) / "graph.sqlite"
    if path.resolve() != path.absolute():
        raise ValueError("Linked graph checkpoint path refused")
    sandbox.check_artifacts(run_id, 1048576)
    async with aiosqlite.connect(path) as connection:
        saver = QuotaSqliteSaver(connection, sandbox, run_id)
        with sandbox.admit_artifacts(run_id, 1048576):
            await saver.setup()
        yield saver
