"""Live host-side controller for a secret-free, isolated AppWorld worker."""

from __future__ import annotations

import argparse
import json
import queue
import subprocess
import threading
from pathlib import Path

from .checkpoints import IntegrityError, RunStore, canonical, digest
from .stateful_adapter import container_command, stop_owned_container


class StreamWorker:
    def __init__(
        self,
        image_id: str,
        bundle: Path,
        store: RunStore,
        run_id: str,
        task_id: str,
        seed: int,
        actions: list[str] | None = None,
    ):
        RunStore._validate_components("runs", run_id)
        if store.root is None:
            raise ValueError("persistent stream evidence required")
        manifest = RunStore(bundle).read("manifest", "public_bundle")
        if manifest is None or task_id not in manifest["task_ids"]:
            raise ValueError("stream task is not in the declared train bundle")
        self.store, self.run_id = store, run_id
        self.name = "copromem-c05-" + run_id
        self.output = store.root.resolve() / "native" / run_id
        if self.output.exists():
            raise FileExistsError("stream output must be new")
        self.output.mkdir(parents=True)
        self.request = {
            "task_id": task_id,
            "seed": seed,
            "actions": list(actions or []),
        }
        self.store.write("stream_initial_requests", run_id, self.request)
        command = container_command(image_id, bundle, self.output, self.name) + [
            "--stream"
        ]
        self.store.write(
            "worker_commands", run_id, {"command": command, "image_id": image_id}
        )
        self.lines: queue.Queue[str | None] = queue.Queue()
        self.stdout, self.stderr = [], []
        self.frame_index = 0
        self.last = None
        self.closed = False
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )

        def collect_stdout():
            for line in self.process.stdout:
                self.stdout.append(line)
                self.lines.put(line)
            self.lines.put(None)

        def collect_stderr():
            self.stderr.extend(self.process.stderr)

        self.readers = [
            threading.Thread(target=collect_stdout, daemon=True),
            threading.Thread(target=collect_stderr, daemon=True),
        ]
        for reader in self.readers:
            reader.start()
        try:
            self._send(self.request)
            self.last = self._receive()
        except Exception:
            self.close(send_close=False)
            raise

    def _send(self, value: dict) -> None:
        self.process.stdin.write(canonical(value) + "\n")
        self.process.stdin.flush()

    def _receive(self, *, final: bool = False) -> dict:
        while True:
            try:
                line = self.lines.get(timeout=45)
            except queue.Empty as exc:
                raise TimeoutError("isolated stream did not respond") from exc
            if line is None:
                raise RuntimeError("isolated stream exited before its response")
            prefix = "COPROMEM_WORKER_DONE=" if final else "COPROMEM_WORKER_RESULT="
            if not line.startswith(prefix):
                continue
            frame = json.loads(line[len(prefix) :])
            if (
                frame["request_id"] != digest(self.request)
                or frame["task_id"] != self.request["task_id"]
            ):
                raise IntegrityError(
                    "stream frame does not match the recorded action prefix"
                )
            self.store.write(
                "stream_frames", f"{self.run_id}-{self.frame_index:03d}", frame
            )
            self.frame_index += 1
            return frame

    def act(self, program: str) -> dict:
        if self.closed or len(self.request["actions"]) >= self.last.get(
            "action_limit", 20
        ):
            raise ValueError("stream closed or native action cap reached")
        self.request = {**self.request, "actions": [*self.request["actions"], program]}
        self.store.write(
            "stream_inputs",
            f"{self.run_id}-{len(self.request['actions']):03d}",
            {"program": program, "prefix_id": digest(self.request)},
        )
        self._send({"program": program})
        self.last = self._receive()
        return self.last

    def close(self, *, send_close: bool = True) -> None:
        if self.closed:
            return
        self.closed = True
        closure_error = None
        try:
            if send_close and self.process.poll() is None:
                self._send({"close": True})
                self.last = self._receive(final=True)
            self.process.wait(timeout=15)
        except Exception as exc:  # noqa: BLE001 - contain the worker on any controller failure
            closure_error = type(exc).__name__
            stop_owned_container(self.name, self.output)
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        finally:
            for reader in self.readers:
                reader.join(timeout=1)
            record = {
                "exit_code": self.process.poll(),
                "stdout": "".join(self.stdout),
                "stderr": "".join(self.stderr),
                "closure_error_type": closure_error,
            }
            self.store.write("worker_processes", self.run_id, record)
            self.store.write("worker_requests", self.run_id, self.request)
            if (
                self.last is not None
                and record["exit_code"] == 0
                and closure_error is None
            ):
                self.store.write("worker_results", self.run_id, self.last)
            elif self.last is not None:
                self.store.write("partial_worker_results", self.run_id, self.last)
            for pipe in (self.process.stdin, self.process.stdout, self.process.stderr):
                pipe.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8"))
    with StreamWorker(
        args.image_id,
        args.bundle,
        RunStore(args.store),
        args.run_id,
        request["task_id"],
        request["seed"],
    ) as worker:
        for program in request["actions"]:
            worker.act(program)
    print(
        json.dumps(
            {
                "run_id": args.run_id,
                "state_digest": worker.last["state_digest"],
                "frames": worker.frame_index,
                "unsupported": worker.last["harness_only_state"]["namespace"][
                    "unsupported"
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
