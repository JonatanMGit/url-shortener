from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib import error, request


ROOT = Path(__file__).resolve().parents[4]
PERF_DIR = ROOT / "load-testing" / "scalability" / "performance"
RESULTS_DIR = PERF_DIR / "results"
DOCKER_DIR = ROOT / "load-testing" / "scalability" / "docker"
PERF_COMPOSE_FILE = DOCKER_DIR / "docker-compose.performance.yml"


@dataclass(frozen=True)
class Stage:
    concurrency: int
    duration_seconds: int
    think_seconds: float = 0.05


SCENARIO_BY_TIER: dict[str, list[Stage]] = {
    "bronze": [Stage(concurrency=50, duration_seconds=60, think_seconds=0.05)],
    "silver": [
        Stage(concurrency=50, duration_seconds=30, think_seconds=0.05),
        Stage(concurrency=120, duration_seconds=30, think_seconds=0.05),
        Stage(concurrency=200, duration_seconds=60, think_seconds=0.05),
        Stage(concurrency=200, duration_seconds=30, think_seconds=0.05),
    ],
    "gold": [Stage(concurrency=250, duration_seconds=120, think_seconds=0.01)],
}

SEED_COUNT_BY_TIER = {
    "bronze": 25,
    "silver": 50,
    "gold": 100,
}


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


NO_REDIRECT_OPENER = request.build_opener(_NoRedirect())


def run_command(command: list[str], *, env: dict[str, str] | None = None, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    print("$", " ".join(command))
    return subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=capture_output,
        check=False,
    )


def ensure_results_dir() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def to_repo_relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def is_compose_nginx_running() -> bool:
    command = [
        "docker",
        "compose",
        "-f",
        str(PERF_COMPOSE_FILE),
        "ps",
        "--services",
        "--filter",
        "status=running",
    ]
    result = run_command(command, capture_output=True)
    if result.returncode != 0:
        return False
    running_services = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    return "nginx" in running_services


def start_stack() -> int:
    command = [
        "docker",
        "compose",
        "-f",
        str(PERF_COMPOSE_FILE),
        "up",
        "-d",
        "--build",
    ]
    result = run_command(command)
    return result.returncode


def stop_stack() -> int:
    command = [
        "docker",
        "compose",
        "-f",
        str(PERF_COMPOSE_FILE),
        "down",
        "-v",
    ]
    result = run_command(command)
    return result.returncode


def capture_docker_ps() -> int:
    ensure_results_dir()
    output_path = RESULTS_DIR / f"docker-ps-{now_stamp()}.txt"

    result = run_command(["docker", "ps"], capture_output=True)
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return result.returncode

    output_path.write_text(result.stdout, encoding="utf-8")
    print(f"Saved: {to_repo_relative(output_path)}")
    return 0


def _json_request(method: str, url: str, payload: dict | None = None, timeout: float = 5.0) -> tuple[int, dict | None, str | None]:
    headers = {}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")

    req = request.Request(url, data=body, headers=headers, method=method)
    try:
        with NO_REDIRECT_OPENER.open(req, timeout=timeout) as response:
            status = response.getcode()
            raw_body = response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        status = exc.code
        raw_body = exc.read().decode("utf-8", errors="replace")
    except Exception as exc:  # pragma: no cover - network errors are environment-dependent
        return 0, None, str(exc)

    parsed: dict | None = None
    if raw_body:
        try:
            loaded = json.loads(raw_body)
            if isinstance(loaded, dict):
                parsed = loaded
        except json.JSONDecodeError:
            parsed = None

    return status, parsed, None


def _unique_suffix() -> str:
    return f"{int(time.time() * 1000)}-{random.randint(100000, 999999)}"


def seed_short_codes(base_url: str, count: int) -> list[str]:
    base = base_url.rstrip("/")
    suffix = _unique_suffix()

    user_payload = {
        "username": f"py_load_user_{suffix}",
        "email": f"py_load_{suffix}@example.com",
    }
    status, user_body, error_message = _json_request("POST", f"{base}/users", user_payload)
    if error_message:
        raise RuntimeError(f"Unable to create seed user: {error_message}")
    if status != 201 or not user_body or "id" not in user_body:
        raise RuntimeError(f"Unable to create seed user. status={status} body={user_body}")

    user_id = user_body["id"]
    short_codes: list[str] = []
    for i in range(count):
        url_payload = {
            "user_id": user_id,
            "original_url": f"https://example.com/load/{suffix}/{i}",
            "title": f"Python load test {i}",
        }
        status, url_body, error_message = _json_request("POST", f"{base}/urls", url_payload)
        if error_message:
            raise RuntimeError(f"Unable to create seed URL {i}: {error_message}")
        if status != 201 or not url_body or "short_code" not in url_body:
            raise RuntimeError(f"Unable to create seed URL {i}. status={status} body={url_body}")
        short_codes.append(str(url_body["short_code"]))

    return short_codes


def hit_resolve(base_url: str, short_codes: list[str], timeout: float = 5.0) -> tuple[bool, float, int]:
    short_code = random.choice(short_codes)
    url = f"{base_url.rstrip('/')}/r/{short_code}"
    req = request.Request(url, method="GET")

    started = time.perf_counter()
    status = 0
    try:
        with NO_REDIRECT_OPENER.open(req, timeout=timeout) as response:
            status = response.getcode()
            response.read()
    except error.HTTPError as exc:
        status = exc.code
        exc.read()
    except Exception:
        status = 0

    latency_ms = (time.perf_counter() - started) * 1000.0
    return status == 302, latency_ms, status


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total = 0
        self._failed = 0
        self._latencies_ms: list[float] = []
        self._status_counts: dict[str, int] = {}

    def record(self, success: bool, latency_ms: float, status: int) -> None:
        key = str(status)
        with self._lock:
            self._total += 1
            if not success:
                self._failed += 1
            self._latencies_ms.append(latency_ms)
            self._status_counts[key] = self._status_counts.get(key, 0) + 1

    def summarize(self, elapsed_seconds: float) -> dict:
        with self._lock:
            total = self._total
            failed = self._failed
            latencies = sorted(self._latencies_ms)
            status_counts = dict(self._status_counts)

        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
        max_latency = max(latencies) if latencies else 0.0
        p95_latency = 0.0
        if latencies:
            p95_index = max(0, int(len(latencies) * 0.95) - 1)
            p95_latency = latencies[p95_index]

        request_rate = (total / elapsed_seconds) if elapsed_seconds > 0 else 0.0
        error_rate = (failed / total) if total else 0.0
        success_rate = 1.0 - error_rate if total else 0.0

        return {
            "total_requests": total,
            "failed_requests": failed,
            "successful_requests": max(total - failed, 0),
            "elapsed_seconds": elapsed_seconds,
            "request_rate": request_rate,
            "error_rate": error_rate,
            "success_rate": success_rate,
            "p95_latency_ms": p95_latency,
            "avg_latency_ms": avg_latency,
            "max_latency_ms": max_latency,
            "status_counts": status_counts,
        }


def run_stage(base_url: str, short_codes: list[str], stage: Stage, metrics: Metrics) -> None:
    deadline = time.monotonic() + stage.duration_seconds

    def worker() -> None:
        while time.monotonic() < deadline:
            success, latency_ms, status = hit_resolve(base_url, short_codes)
            metrics.record(success, latency_ms, status)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if stage.think_seconds > 0:
                time.sleep(min(stage.think_seconds, remaining))

    workers = [
        threading.Thread(target=worker, daemon=True, name=f"load-worker-{index}")
        for index in range(stage.concurrency)
    ]
    for worker_thread in workers:
        worker_thread.start()
    for worker_thread in workers:
        worker_thread.join()


def _resolve_output_path(env_name: str, default_path: Path) -> Path:
    env_value = os.environ.get(env_name)
    if not env_value:
        return default_path
    configured_path = Path(env_value)
    if configured_path.is_absolute():
        return configured_path
    return ROOT / configured_path


def _format_percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def _format_ms(value: float) -> str:
    return f"{value:.2f} ms"


def write_summary_files(tier: str, base_url: str, summary: dict, json_path: Path, md_path: Path) -> None:
    timestamp = dt.datetime.now().isoformat()
    payload = {
        "scenario": tier,
        "timestamp": timestamp,
        "base_url": base_url,
        "metrics": summary,
    }

    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    markdown = (
        f"# {tier.upper()} Load Test Summary\n\n"
        f"- Timestamp: {timestamp}\n"
        f"- Base URL: {base_url}\n\n"
        "## Key Metrics\n\n"
        "| Metric | Value |\n"
        "|---|---:|\n"
        f"| p95 latency | {_format_ms(summary['p95_latency_ms'])} |\n"
        f"| Avg latency | {_format_ms(summary['avg_latency_ms'])} |\n"
        f"| Max latency | {_format_ms(summary['max_latency_ms'])} |\n"
        f"| Request rate | {summary['request_rate']:.2f} req/s |\n"
        f"| Error rate | {_format_percent(summary['error_rate'])} |\n"
        f"| Success rate | {_format_percent(summary['success_rate'])} |\n"
    )
    md_path.write_text(markdown, encoding="utf-8")


def run_load(tier: str, base_url: str) -> int:
    ensure_results_dir()

    stages = SCENARIO_BY_TIER[tier]
    timestamp = now_stamp()
    json_output = _resolve_output_path("RESULT_JSON_PATH", RESULTS_DIR / f"{tier}-{timestamp}.json")
    md_output = _resolve_output_path("RESULT_MD_PATH", RESULTS_DIR / f"{tier}-{timestamp}.md")

    seed_count = SEED_COUNT_BY_TIER[tier]
    print(f"Seeding {seed_count} short codes for tier '{tier}'...")
    try:
        short_codes = seed_short_codes(base_url, seed_count)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    metrics = Metrics()
    started = time.perf_counter()
    for index, stage in enumerate(stages, start=1):
        print(
            f"Stage {index}/{len(stages)}: "
            f"concurrency={stage.concurrency}, duration={stage.duration_seconds}s, think={stage.think_seconds}s"
        )
        run_stage(base_url, short_codes, stage, metrics)

    elapsed_seconds = time.perf_counter() - started
    summary = metrics.summarize(elapsed_seconds)
    write_summary_files(tier, base_url, summary, json_output, md_output)

    print(f"Scenario: {tier}")
    print(f"Base URL: {base_url}")
    print(f"p95 latency: {_format_ms(summary['p95_latency_ms'])}")
    print(f"error rate: {_format_percent(summary['error_rate'])}")
    print(f"success rate: {_format_percent(summary['success_rate'])}")
    print(f"Saved: {to_repo_relative(json_output)}")
    print(f"Saved: {to_repo_relative(md_output)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Platform-independent scalability tooling")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("start-stack", help="Start Docker production stack")
    subparsers.add_parser("stop-stack", help="Stop Docker production stack")
    subparsers.add_parser("capture-docker-ps", help="Save docker ps snapshot to results")

    run_parser = subparsers.add_parser("run-load", help="Run a Python load-test scenario")
    run_parser.add_argument("--tier", choices=["bronze", "silver", "gold"], required=True)
    run_parser.add_argument("--base-url", default="http://127.0.0.1:5000")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "start-stack":
        return start_stack()
    if args.command == "stop-stack":
        return stop_stack()
    if args.command == "capture-docker-ps":
        return capture_docker_ps()
    if args.command == "run-load":
        return run_load(args.tier, args.base_url)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
