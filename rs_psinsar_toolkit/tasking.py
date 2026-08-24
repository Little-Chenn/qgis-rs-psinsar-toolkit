"""Pure-Python run lifecycle primitives shared by future M5 modules."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from .localization import tr


_TR_CONTEXT = "@default"


def _tr(source: str) -> str:
    return tr(_TR_CONTEXT, source)


class RunStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PASS = "PASS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class TaskSpec:
    module_id: str
    module_version: str
    inputs: dict[str, Any]
    parameters: dict[str, Any]


@dataclass
class RunContext:
    run_dir: Path
    metadata_dir: Path
    spec: TaskSpec
    status: RunStatus = RunStatus.CREATED

    @classmethod
    def create(
        cls,
        output_root: str | Path,
        spec: TaskSpec,
        run_id: str | None = None,
        metadata_subdir: str | None = None,
    ) -> "RunContext":
        root = Path(output_root).expanduser().resolve()
        if not root.is_dir():
            raise NotADirectoryError(
                _tr("输出根目录不存在：{path}").format(path=root)
            )
        if not spec.module_id.strip():
            raise ValueError(_tr("module_id不能为空。"))
        if run_id is None:
            timestamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S")
            run_id = f"{timestamp}_{spec.module_id}"
        if Path(run_id).name != run_id or run_id in {"", ".", ".."}:
            raise ValueError(_tr("run_id必须是单一安全目录名。"))

        if metadata_subdir is not None:
            if (
                Path(metadata_subdir).name != metadata_subdir
                or metadata_subdir in {"", ".", ".."}
            ):
                raise ValueError(
                    _tr("metadata_subdir必须是单一安全目录名。")
                )
        run_dir = root / run_id
        run_dir.mkdir(exist_ok=False)
        metadata_dir = run_dir
        if metadata_subdir is not None:
            metadata_dir = run_dir / metadata_subdir
            metadata_dir.mkdir(exist_ok=False)
        context = cls(
            run_dir=run_dir,
            metadata_dir=metadata_dir,
            spec=spec,
        )
        context._write_json_exclusive(
            "run_manifest.json",
            {
                "schema_version": 1,
                "created_utc": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"
                ),
                "output_policy": "new run directory; refuse overwrite",
                "task": asdict(spec),
                "status": context.status.value,
            },
        )
        return context

    def mark_running(self) -> None:
        self._transition(RunStatus.RUNNING)

    def mark_pass(self, result: dict[str, Any]) -> None:
        self._write_json_exclusive("result.json", result)
        self._transition(RunStatus.PASS)

    def mark_failed(self, error: BaseException) -> None:
        self._write_json_exclusive(
            "failure_report.json",
            {
                "error_type": type(error).__name__,
                "error": str(error),
            },
        )
        self._transition(RunStatus.FAILED)

    def mark_cancelled(self, reason: str) -> None:
        self._write_text_exclusive(
            "RUN_CANCELLED.md",
            f"# Run cancelled\n\n{reason.strip() or 'User requested cancellation.'}\n",
        )
        self._transition(RunStatus.CANCELLED)

    def _transition(self, target: RunStatus) -> None:
        allowed = {
            RunStatus.CREATED: {RunStatus.RUNNING},
            RunStatus.RUNNING: {
                RunStatus.PASS,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
            },
        }
        if target not in allowed.get(self.status, set()):
            raise RuntimeError(
                _tr("不允许的任务状态转换：{source} -> {target}").format(
                    source=self.status.value,
                    target=target.value,
                )
            )
        self.status = target
        self._write_json_exclusive(
            f"status_{target.value.lower()}.json",
            {
                "status": target.value,
                "updated_utc": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"
                ),
            },
        )

    def _write_json_exclusive(self, name: str, value: Any) -> None:
        payload = json.dumps(value, ensure_ascii=False, indent=2, default=str)
        self._write_text_exclusive(name, payload + "\n")

    def _write_text_exclusive(self, name: str, value: str) -> None:
        path = self.metadata_dir / name
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(value)
