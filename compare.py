#!/usr/bin/env python3
"""MetaSSR vs Other Frameworks - Benchmark Comparison"""

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR
COMPARE_DIR = SCRIPT_DIR / "apps"

# Colors
class C:
    R = '\033[0;31m'
    G = '\033[0;32m'
    Y = '\033[1;33m'
    B = '\033[0;34m'
    NC = '\033[0m'

def log(msg): print(f"{C.B}[INFO]{C.NC} {msg}")
def error(msg): print(f"{C.R}[ERROR]{C.NC} {msg}", file=sys.stderr)
def success(msg): print(f"{C.G}[OK]{C.NC} {msg}")

SCENARIOS = [
    ("Light",  1,  10,  5),
    ("Medium", 4,  50,  5),
    ("Heavy",  8,  200, 5),
    ("Stress", 12, 500, 5),
]

FRAMEWORKS = {
    "metassr": {
        "name": "MetaSSR",
        "port": 8080,
        "docker_image": "metassr-bench",
        "dockerfile": "Dockerfile.metassr",
        "app_dir": "metassr-app",
    },
    "nextjs": {
        "name": "Next.js",
        "port": 3001,
        "docker_image": "nextjs-bench",
        "dockerfile": "Dockerfile.nextjs",
        "app_dir": "nextjs-app",
    },
}

# --- helpers ---

def check_deps(use_docker):
    missing = []
    for dep in ["wrk", "curl"]:
        if subprocess.run(["which", dep], capture_output=True).returncode != 0:
            missing.append(dep)
    if use_docker:
        if subprocess.run(["which", "docker"], capture_output=True).returncode != 0:
            missing.append("docker")
    if missing:
        error(f"Missing: {', '.join(missing)}")
        sys.exit(1)

def wait_for(url, timeout=60):
    for _ in range(timeout):
        try:
            r = subprocess.run(["curl", "-s", "--max-time", "2", url], capture_output=True)
            if r.returncode == 0:
                return True
        except:
            pass
        time.sleep(1)
    return False

def parse_latency_ms(s):
    if not s:
        return 0
    m = re.match(r'([\d.]+)(\w+)', s)
    if not m:
        return 0
    v, u = float(m.group(1)), m.group(2).lower()
    if u == 'us': return v / 1000
    if u == 'ms': return v
    if u == 's': return v * 1000
    return v

def parse_wrk(output):
    r = {"rps": 0, "latency": "0ms", "latency_ms": 0, "p99": "0ms", "p99_ms": 0, "requests": 0, "errors": 0}
    m = re.search(r'Requests/sec:\s+([\d.]+)', output)
    if m: r["rps"] = float(m.group(1))
    m = re.search(r'Latency\s+([\d.]+\w+)', output)
    if m: r["latency"] = m.group(1); r["latency_ms"] = parse_latency_ms(m.group(1))
    m = re.search(r'99%\s+([\d.]+\w+)', output)
    if m: r["p99"] = m.group(1); r["p99_ms"] = parse_latency_ms(m.group(1))
    m = re.search(r'(\d+)\s+requests in', output)
    if m: r["requests"] = int(m.group(1))
    m = re.search(r'Socket errors:.*?(\d+)', output)
    if m: r["errors"] = int(m.group(1))
    return r

def get_system_info():
    info = {
        "os": platform.system(), "os_version": platform.release(),
        "arch": platform.machine(), "cpu": "Unknown",
        "cpu_cores": os.cpu_count() or 0, "memory_gb": 0,
    }
    try:
        if platform.system() == "Linux":
            for line in open("/proc/cpuinfo"):
                if "model name" in line:
                    info["cpu"] = line.split(":")[1].strip(); break
            for line in open("/proc/meminfo"):
                if "MemTotal" in line:
                    info["memory_gb"] = round(int(line.split()[1]) / 1024 / 1024, 1); break
    except:
        pass
    return info

# --- docker ---

def docker_build(fw_key):
    fw = FRAMEWORKS[fw_key]
    log(f"Building Docker image for {fw['name']}...")
    
    cmd = [
        "docker", "build",
        "-t", fw["docker_image"],
        "-f", str(COMPARE_DIR / fw["dockerfile"]),
        str(COMPARE_DIR),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    
    if r.returncode != 0:
        error(f"Docker build failed for {fw['name']}:\n{r.stderr[-500:]}")
        return False
    return True

def docker_start(fw):
    container = fw["docker_image"] + "-run"
    subprocess.run(["docker", "rm", "-f", container], capture_output=True)
    log(f"Starting Docker container for {fw['name']} on port {fw['port']}...")
    cmd = [
        "docker", "run", "-d",
        "--name", container,
        "-p", f"{fw['port']}:{fw['port']}",
        fw["docker_image"],
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        error(f"Docker start failed for {fw['name']}:\n{r.stderr}")
        return None
    return container

def docker_stop(container):
    if container:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True)

# --- local ---

def local_build(fw_key):
    """Build a framework app locally."""
    fw = FRAMEWORKS[fw_key]
    app_dir = COMPARE_DIR / fw["app_dir"]
    
    if not app_dir.exists():
        error(f"App directory not found: {app_dir}")
        return False
    
    log(f"Installing {fw['name']} dependencies...")
    r = subprocess.run(["npm", "install"], cwd=app_dir, capture_output=True, text=True)
    if r.returncode != 0:
        error(f"npm install failed for {fw['name']}:\n{r.stderr[-300:]}")
        return False

    if fw_key == "metassr":
        # Build MetaSSR binary first if not available
        metassr_bin = shutil.which("metassr")
        if not metassr_bin:
            log("Building MetaSSR from source...")
            r = subprocess.run(["cargo", "build", "--release"], cwd=PROJECT_ROOT, capture_output=True, text=True)
            if r.returncode != 0:
                error(f"MetaSSR build failed:\n{r.stderr[-300:]}")
                return False
        
        log("Building MetaSSR app...")
        r = subprocess.run(["npm", "run", "build"], cwd=app_dir, capture_output=True, text=True)
        if r.returncode != 0:
            error(f"MetaSSR app build failed:\n{r.stderr[-300:]}")
            return False
    elif fw_key == "nextjs":
        if not (app_dir / ".next").exists():
            log("Building Next.js app...")
            r = subprocess.run(["npm", "run", "build"], cwd=app_dir, capture_output=True, text=True)
            if r.returncode != 0:
                error(f"Next.js build failed:\n{r.stderr[-300:]}")
                return False
    
    return True

def local_start(fw_key):
    """Start a framework server locally."""
    fw = FRAMEWORKS[fw_key]
    app_dir = COMPARE_DIR / fw["app_dir"]
    
    log(f"Starting {fw['name']} server on port {fw['port']}...")
    proc = subprocess.Popen(
        ["npm", "start"], cwd=app_dir,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return proc

# --- benchmark ---

def run_scenarios(url):
    results = []
    for name, threads, conns, dur in SCENARIOS:
        print(f"  {C.Y}[{name}]{C.NC} t={threads} c={conns} d={dur}s ... ", end="", flush=True)
        cmd = ["wrk", f"-t{threads}", f"-c{conns}", f"-d{dur}s", "--latency", url]
        r = subprocess.run(cmd, capture_output=True, text=True)
        m = parse_wrk(r.stdout + r.stderr)
        print(f"{m['rps']:.0f} RPS | {m['latency']} avg | {m['p99']} p99")
        results.append({"name": name, "threads": threads, "connections": conns, "duration": dur, **m})
    return results

# --- report ---

def pct_diff(a, b):
    if b == 0: return 0
    return ((a - b) / b) * 100

def generate_report(all_results, output_dir, system_info, use_docker):
    labels = ", ".join(f'"{s[0]}"' for s in SCENARIOS)
    fw_names = list(all_results.keys())

    report = f"""# MetaSSR Framework Comparison

**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Mode:** {"Docker containers" if use_docker else "Local processes"}

## System Information

| Property | Value |
|----------|-------|
| OS | {system_info['os']} {system_info['os_version']} |
| Architecture | {system_info['arch']} |
| CPU | {system_info['cpu']} |
| CPU Cores | {system_info['cpu_cores']} |
| Memory | {system_info['memory_gb']} GB |

## Frameworks Tested

| Framework | Port | Mode |
|-----------|------|------|
"""
    for k in fw_names:
        report += f"| {FRAMEWORKS[k]['name']} | {FRAMEWORKS[k]['port']} | {'Docker' if use_docker else 'Local'} |\n"

    # --- charts ---
    for title, key, unit, fmt in [
        ("Requests per Second", "rps", "RPS", "d"),
        ("Average Latency", "latency_ms", "ms", ".2f"),
        ("P99 Latency", "p99_ms", "ms", ".2f"),
    ]:
        max_val = 0
        for fw_key in fw_names:
            for r in all_results[fw_key]:
                max_val = max(max_val, r[key])
        max_val = max_val * 1.2

        # Build interleaved labels and values: "Light - MetaSSR", "Light - Next.js", ...
        combined_labels = []
        combined_vals = []
        for s_idx, (sname, _, _, _) in enumerate(SCENARIOS):
            for fw_key in fw_names:
                combined_labels.append(f'"{sname} - {FRAMEWORKS[fw_key]["name"]}"')
                combined_vals.append(all_results[fw_key][s_idx][key])

        labels_str = ", ".join(combined_labels)
        if fmt == "d":
            vals_str = ", ".join(str(int(v)) for v in combined_vals)
        else:
            vals_str = ", ".join(f"{v:{fmt}}" for v in combined_vals)

        report += f"\n## {title}\n\n"
        report += f"```mermaid\nxychart-beta\n"
        report += f'    title "{title}"\n'
        report += f"    x-axis [{labels_str}]\n"
        if fmt == "d":
            report += f'    y-axis "{unit}" 0 --> {int(max_val)}\n'
        else:
            report += f'    y-axis "{unit}" 0 --> {max_val:{fmt}}\n'
        report += f"    bar [{vals_str}]\n"
        report += "```\n\n"

    # --- detailed tables per scenario ---
    report += "## Detailed Results\n\n"
    for i, (sname, thr, conn, dur) in enumerate(SCENARIOS):
        report += f"### {sname} Load (t={thr} c={conn} d={dur}s)\n\n"
        report += "| Framework | RPS | Avg Latency | P99 Latency | Requests | Errors |\n"
        report += "|-----------|-----|-------------|-------------|----------|--------|\n"
        for fw_key in fw_names:
            r = all_results[fw_key][i]
            err = f"FAIL ({r['errors']})" if r["errors"] > 0 else "OK"
            report += f"| {FRAMEWORKS[fw_key]['name']} | {int(r['rps']):,} | {r['latency']} | {r['p99']} | {r['requests']:,} | {err} |\n"
        report += "\n"

    # --- summary table ---
    report += "## Summary\n\n"
    report += "| Metric | " + " | ".join(FRAMEWORKS[k]["name"] for k in fw_names) + " |\n"
    report += "|--------|" + "|".join("---" for _ in fw_names) + "|\n"

    for label, key, fmt in [
        ("Avg RPS", "rps", ",.0f"),
        ("Avg Latency (ms)", "latency_ms", ".2f"),
        ("Avg P99 (ms)", "p99_ms", ".2f"),
        ("Total Requests", "requests", ","),
    ]:
        cells = []
        for fw_key in fw_names:
            data = all_results[fw_key]
            if key == "requests":
                v = sum(r[key] for r in data)
            else:
                v = sum(r[key] for r in data) / len(data)
            cells.append(f"{v:{fmt}}")
        report += f"| {label} | " + " | ".join(cells) + " |\n"

    # --- head-to-head ---
    if "metassr" in all_results and len(fw_names) > 1:
        report += "\n## Head-to-Head\n"
        metassr_data = all_results["metassr"]
        for fw_key in fw_names:
            if fw_key == "metassr":
                continue
            other_data = all_results[fw_key]
            report += f"\n### MetaSSR vs {FRAMEWORKS[fw_key]['name']}\n\n"
            report += "| Scenario | RPS Diff | Latency Diff | P99 Diff | Winner |\n"
            report += "|----------|----------|-------------|----------|--------|\n"
            for i, (sname, _, _, _) in enumerate(SCENARIOS):
                m = metassr_data[i]
                o = other_data[i]
                rps_d = pct_diff(m["rps"], o["rps"])
                lat_d = pct_diff(m["latency_ms"], o["latency_ms"])
                p99_d = pct_diff(m["p99_ms"], o["p99_ms"])
                # Winner: higher RPS is better, lower latency is better
                rps_winner = "MetaSSR" if m["rps"] >= o["rps"] else FRAMEWORKS[fw_key]["name"]
                report += f"| {sname} | {'+' if rps_d >= 0 else ''}{rps_d:.1f}% | {'+' if lat_d >= 0 else ''}{lat_d:.1f}% | {'+' if p99_d >= 0 else ''}{p99_d:.1f}% | {rps_winner} |\n"
            report += "\nPositive RPS diff = MetaSSR faster. Negative latency diff = MetaSSR faster.\n"

    output_dir = output_dir / str(datetime.now().strftime('%Y-%m-%d-%H-%M-%S'))
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.md").write_text(report)
    (output_dir / "report.json").write_text(json.dumps({
        "timestamp": datetime.now().isoformat(),
        "system": system_info,
        "mode": "docker" if use_docker else "local",
        "frameworks": {k: all_results[k] for k in fw_names},
    }, indent=2))

    print(f"Reports Saved to {output_dir}")
    return report

# --- main ---

def main():
    parser = argparse.ArgumentParser(description="MetaSSR Framework Comparison Benchmark")
    parser.add_argument("-f", "--frameworks", nargs="+", default=["metassr", "nextjs"],
                        choices=list(FRAMEWORKS.keys()),
                        help="Frameworks to benchmark (default: metassr nextjs)")
    parser.add_argument("-o", "--output", default=".bench/apps", help="Output directory")
    parser.add_argument("-d", "--docker", action="store_true", help="Run servers in Docker containers")
    parser.add_argument("--skip-build", action="store_true", help="Skip build step (local mode)")
    args = parser.parse_args()

    print(f"{C.B}=== MetaSSR Framework Comparison ==={C.NC}")
    check_deps(args.docker)
    system_info = get_system_info()
    log(f"System: {system_info['os']} {system_info['arch']}, {system_info['cpu_cores']} cores, {system_info['memory_gb']}GB RAM")
    log(f"Mode: {'Docker' if args.docker else 'Local'}")
    log(f"Frameworks: {', '.join(FRAMEWORKS[f]['name'] for f in args.frameworks)}")

    output_dir = PROJECT_ROOT / args.output
    all_results = {}
    containers = []
    processes = []

    try:
        for fw_key in args.frameworks:
            fw = FRAMEWORKS[fw_key]
            url = f"http://localhost:{fw['port']}"

            print(f"\n{C.B}--- {fw['name']} ---{C.NC}")

            if args.docker:
                if not docker_build(fw_key):
                    error(f"Skipping {fw['name']}")
                    continue
                container = docker_start(fw)
                if not container:
                    error(f"Skipping {fw['name']}")
                    continue
                containers.append(container)
            else:
                # Check if already running
                if wait_for(url, timeout=2):
                    log(f"{fw['name']} already running on port {fw['port']}")
                else:
                    if not args.skip_build:
                        if not local_build(fw_key):
                            error(f"Skipping {fw['name']}")
                            continue
                    proc = local_start(fw_key)
                    processes.append(proc)

            log(f"Waiting for {fw['name']}...")
            if not wait_for(url, timeout=60):
                error(f"{fw['name']} did not start, skipping")
                continue

            log("Warming up...")
            for _ in range(10):
                subprocess.run(["curl", "-s", url], capture_output=True)
            time.sleep(2)

            log(f"Benchmarking {fw['name']}...")
            all_results[fw_key] = run_scenarios(url)
            success(f"{fw['name']} benchmarks complete")

    finally:
        log("Cleaning up...")
        for container in containers:
            docker_stop(container)
        for proc in processes:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    if not all_results:
        error("No benchmark results collected")
        sys.exit(1)

    report = generate_report(all_results, output_dir, system_info, args.docker)

if __name__ == "__main__":
    main()