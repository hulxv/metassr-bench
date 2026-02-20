# MetaSSR Benchmarks

Standalone performance benchmarking and framework comparison for MetaSSR.

## Quick Start

### MetaSSR Benchmark

```bash
# Start your MetaSSR server first, then:
python3 benchmarks/benchmark.py

# Or with options:
python3 benchmarks/benchmark.py --port 3000 --skip-build

# Analyze existing results:
python3 benchmarks/benchmark.py --analyze-only .bench/results.json
```

### Framework Comparison

```bash
# Local mode (build and run servers locally):
python3 benchmarks/apps.py

# Docker mode (recommended for fair comparison):
python3 benchmarks/apps.py --docker

# Compare specific frameworks:
python3 benchmarks/compare.py --frameworks metassr nextjs

# Skip build (servers already running):
python3 benchmarks/compare.py --skip-build
```

## Requirements

- `wrk` - HTTP benchmarking tool
- `curl` - HTTP client
- `docker` - For containerized benchmarks (optional)
- Python 3.6+

Install on Ubuntu/Debian:
```bash
sudo apt-get install wrk curl python3
```

## Output

### benchmark.py
Results saved to `.bench/`:
- `results.json` - Raw benchmark data with system info
- `summary.md` - Summary with Mermaid charts

### compare.py
Results saved to `.bench/apps/`:
- `comparison.json` - Raw comparison data
- `comparison.md` - Side-by-side report with charts

## Test Scenarios

| Test   | Threads | Connections | Duration |
| ------ | ------- | ----------- | -------- |
| Light  | 1       | 10          | 20s      |
| Medium | 4       | 50          | 40s      |
| Heavy  | 8       | 200         | 80s      |
| Stress | 12      | 500         | 120s     |

## Options

### benchmark.py

```
-u, --url URL       Server URL (default: http://localhost:8080)
-p, --port PORT     Server port (default: 8080)
-o, --output DIR    Output directory (default: .bench)
-s, --skip-build    Skip building the project
--analyze-only FILE Only analyze existing results.json
```

### compare.py

```
-f, --frameworks    Frameworks to compare (default: metassr nextjs)
-o, --output DIR    Output directory (default: .bench/apps)
-d, --docker        Run servers in Docker containers
--skip-build        Skip build step in local mode
```

## Test Apps

Both test apps render the same page — a list of 20 items with titles and body
text — to ensure a fair SSR comparison. Each app is self-contained with its own
`package.json`, source code, and Dockerfile.

### Adding a New Framework

1. Create `benchmarks/apps/<framework>-app/` with the same page template
2. Create `benchmarks/apps/Dockerfile.<framework>`
3. Add an entry to `FRAMEWORKS` in `apps.py`
