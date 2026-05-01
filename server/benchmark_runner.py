import argparse
import json
import statistics
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request


@dataclass(frozen=True)
class EndpointCase:
    name: str
    method: str
    path: str
    headers: dict[str, str] | None = None
    body: dict[str, Any] | None = None


MANAGER_HEADERS = {
    "x-user-role": "manager",
    "x-user-email": "manager@example.com",
}

INVESTOR_HEADERS = {
    "x-user-role": "investor",
    "x-user-email": "investor@example.com",
}

PHASE1_HEADERS = MANAGER_HEADERS

SCENARIOS: dict[str, list[EndpointCase]] = {
    "smoke": [
        EndpointCase("health", "GET", "/health"),
        EndpointCase("ready", "GET", "/health/ready"),
    ],
    "read_core": [
        EndpointCase("manager_dashboard", "GET", "/dashboard/manager", MANAGER_HEADERS),
        EndpointCase("cycles", "GET", "/cycles", MANAGER_HEADERS),
        EndpointCase("investor_dashboard", "GET", "/dashboard/investor", INVESTOR_HEADERS),
        EndpointCase("portfolio_analytics", "GET", "/analytics/portfolio"),
        EndpointCase("live_activity", "GET", "/live/activity", MANAGER_HEADERS),
    ],
    "phase1_read": [
        EndpointCase("permissions_me", "GET", "/permissions/me", PHASE1_HEADERS),
        EndpointCase("session_policies", "GET", "/admin/security/session-policies", PHASE1_HEADERS),
        EndpointCase("ip_allowlist", "GET", "/admin/security/ip-allowlist", PHASE1_HEADERS),
        EndpointCase("help_content", "GET", "/help-content", PHASE1_HEADERS),
        EndpointCase("audit_events", "GET", "/audit/events", PHASE1_HEADERS),
        EndpointCase("onboarding_overview", "GET", "/companies/onboarding/overview", PHASE1_HEADERS),
    ],
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if p <= 0:
        return min(values)
    if p >= 100:
        return max(values)
    ordered = sorted(values)
    rank = (len(ordered) - 1) * (p / 100.0)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    weight = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def run_single_request(base_url: str, timeout_s: float, case: EndpointCase) -> tuple[int, float, str | None]:
    url = f"{base_url.rstrip('/')}{case.path}"
    payload = None
    headers = {"Content-Type": "application/json"}
    if case.headers:
        headers.update(case.headers)
    if case.body is not None:
        payload = json.dumps(case.body).encode("utf-8")

    start = time.perf_counter()
    req = request.Request(url=url, data=payload, method=case.method, headers=headers)
    try:
        with request.urlopen(req, timeout=timeout_s) as resp:
            _ = resp.read()
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            return resp.status, elapsed_ms, None
    except error.HTTPError as exc:
        _ = exc.read()
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return exc.code, elapsed_ms, f"HTTPError {exc.code}"
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return 0, elapsed_ms, str(exc)


def run_benchmark(
    *,
    base_url: str,
    scenario: str,
    duration_s: int,
    concurrency: int,
    timeout_s: float,
    warmup_s: int,
) -> dict[str, Any]:
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario '{scenario}'. Available: {', '.join(sorted(SCENARIOS))}")

    cases = SCENARIOS[scenario]
    metrics_lock = threading.Lock()
    global_latencies: list[float] = []
    per_case_latencies: dict[str, list[float]] = defaultdict(list)
    per_case_status: dict[str, Counter[int]] = defaultdict(Counter)
    per_case_errors: dict[str, list[str]] = defaultdict(list)

    total_requests = 0
    total_success = 0
    total_failures = 0

    if warmup_s > 0:
        warmup_deadline = time.monotonic() + warmup_s
        while time.monotonic() < warmup_deadline:
            for case in cases:
                run_single_request(base_url, timeout_s, case)

    deadline = time.monotonic() + duration_s

    def worker(worker_id: int):
        nonlocal total_requests, total_success, total_failures
        idx = worker_id % len(cases)
        while time.monotonic() < deadline:
            case = cases[idx % len(cases)]
            idx += 1
            status, elapsed_ms, err = run_single_request(base_url, timeout_s, case)
            success = 200 <= status < 400

            with metrics_lock:
                total_requests += 1
                if success:
                    total_success += 1
                else:
                    total_failures += 1

                global_latencies.append(elapsed_ms)
                per_case_latencies[case.name].append(elapsed_ms)
                per_case_status[case.name][status] += 1
                if err and len(per_case_errors[case.name]) < 20:
                    per_case_errors[case.name].append(err)

    started_at = now_utc()
    run_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for worker_id in range(concurrency):
            pool.submit(worker, worker_id)
    elapsed_s = max(time.perf_counter() - run_start, 0.001)
    finished_at = now_utc()

    global_stats = {
        "count": len(global_latencies),
        "min_ms": round(min(global_latencies), 2) if global_latencies else 0.0,
        "avg_ms": round(statistics.mean(global_latencies), 2) if global_latencies else 0.0,
        "max_ms": round(max(global_latencies), 2) if global_latencies else 0.0,
        "p50_ms": round(percentile(global_latencies, 50), 2),
        "p95_ms": round(percentile(global_latencies, 95), 2),
        "p99_ms": round(percentile(global_latencies, 99), 2),
    }

    per_endpoint: dict[str, Any] = {}
    for case in cases:
        latencies = per_case_latencies.get(case.name, [])
        status_counts = per_case_status.get(case.name, Counter())
        req_count = sum(status_counts.values())
        ok_count = sum(v for code, v in status_counts.items() if 200 <= code < 400)
        fail_count = req_count - ok_count
        per_endpoint[case.name] = {
            "method": case.method,
            "path": case.path,
            "requests": req_count,
            "success": ok_count,
            "failures": fail_count,
            "success_rate": round((ok_count / req_count) * 100.0, 2) if req_count else 0.0,
            "latency_ms": {
                "min": round(min(latencies), 2) if latencies else 0.0,
                "avg": round(statistics.mean(latencies), 2) if latencies else 0.0,
                "max": round(max(latencies), 2) if latencies else 0.0,
                "p95": round(percentile(latencies, 95), 2),
                "p99": round(percentile(latencies, 99), 2),
            },
            "status_codes": dict(sorted(status_counts.items())),
            "sample_errors": per_case_errors.get(case.name, []),
        }

    return {
        "scenario": scenario,
        "base_url": base_url,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds_requested": duration_s,
        "duration_seconds_actual": round(elapsed_s, 2),
        "concurrency": concurrency,
        "timeout_seconds": timeout_s,
        "summary": {
            "total_requests": total_requests,
            "total_success": total_success,
            "total_failures": total_failures,
            "success_rate": round((total_success / total_requests) * 100.0, 2) if total_requests else 0.0,
            "throughput_rps": round(total_requests / elapsed_s, 2),
            "latency_ms": global_stats,
        },
        "endpoints": per_endpoint,
    }


def write_report(report: dict[str, Any], output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def print_summary(report: dict[str, Any]):
    summary = report["summary"]
    latency = summary["latency_ms"]
    print("")
    print("Benchmark Complete")
    print(f"Scenario: {report['scenario']}")
    print(f"Base URL: {report['base_url']}")
    print(f"Requests: {summary['total_requests']} | Success: {summary['total_success']} | Failures: {summary['total_failures']}")
    print(f"Success Rate: {summary['success_rate']}% | Throughput: {summary['throughput_rps']} req/s")
    print(f"Latency ms -> p50: {latency['p50_ms']}, p95: {latency['p95_ms']}, p99: {latency['p99_ms']}, avg: {latency['avg_ms']}")
    print("")
    print("Endpoint Breakdown")
    for name, endpoint in report["endpoints"].items():
        stats = endpoint["latency_ms"]
        print(
            f"- {name} [{endpoint['method']} {endpoint['path']}] "
            f"req={endpoint['requests']} success={endpoint['success_rate']}% "
            f"p95={stats['p95']}ms p99={stats['p99']}ms"
        )


def main():
    parser = argparse.ArgumentParser(description="Simple API benchmark runner for ESG app.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument("--scenario", default="read_core", choices=sorted(SCENARIOS.keys()), help="Benchmark scenario")
    parser.add_argument("--duration", type=int, default=30, help="Test duration in seconds")
    parser.add_argument("--concurrency", type=int, default=8, help="Concurrent worker count")
    parser.add_argument("--timeout", type=float, default=10.0, help="Request timeout in seconds")
    parser.add_argument("--warmup", type=int, default=5, help="Warmup duration in seconds")
    parser.add_argument("--output", default="", help="Path to write JSON report")
    args = parser.parse_args()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    default_output = Path(__file__).resolve().parents[1] / "run-logs" / f"benchmark_{args.scenario}_{timestamp}.json"
    output_path = Path(args.output) if args.output else default_output

    report = run_benchmark(
        base_url=args.base_url,
        scenario=args.scenario,
        duration_s=max(1, args.duration),
        concurrency=max(1, args.concurrency),
        timeout_s=max(0.1, args.timeout),
        warmup_s=max(0, args.warmup),
    )
    write_report(report, output_path)
    print_summary(report)
    print(f"\nReport: {output_path}")


if __name__ == "__main__":
    main()
