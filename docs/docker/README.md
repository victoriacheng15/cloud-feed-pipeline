# Container Image Architecture & Benchmark Analysis

This document details the multi-stage container strategy for the RSS feed extractor, comparing the Debian-based `python:3.12-slim` image and the Alpine-based `python:3.12-alpine` image.

---

## 1. Multi-Stage Container Strategy

Both container variants implement a two-stage build pattern using Astral's `uv` package manager:

1. **Stage 1 (Builder):**
   - Injects the standalone `uv` binary from `ghcr.io/astral-sh/uv:latest`.
   - Freezes and installs dependencies (`uv sync --frozen --no-install-project --no-dev`) into an isolated virtual environment (`/app/.venv`).
   - Compiles bytecode upfront (`UV_COMPILE_BYTECODE=1`) to eliminate runtime startup compilation overhead.
2. **Stage 2 (Runtime):**
   - Copies only the compiled virtual environment and `src/extractor.py`.
   - Omits the `uv` binary, build tools, compiler headers, and temporary caches.
   - Enforces least-privilege security by creating and executing under an unprivileged system user (`extractoruser:extractorgroup`).
   - Compatible with ECS Fargate read-only root filesystems (`readonlyRootFilesystem = true`).

---

## 2. Empirical Benchmark Comparison

Measurements performed locally via Podman using multi-stage builds against identical application sources and dependencies (`boto3`, `feedparser`, `requests`):

| Metric | Debian (slim) | Alpine | Delta |
| :--- | :--- | :--- | :--- |
| **Uncompressed Size (RAM / Disk)** | **177.27 MB** | **108.29 MB** | -68.98 MB (-39%) |
| **Compressed Size (ECR Storage)** | **76.10 MB** | **51.72 MB** | -24.38 MB (-32%) |
| **Monthly ECR Cost (1 Image)** | ~$0.0076 / month | ~$0.0051 / month | -$0.0025 / month |
| **Monthly ECR Cost (3 Retained)** | ~$0.023 / month | ~$0.015 / month | -$0.008 / month |
| **C Standard Library** | `glibc` (GNU C Library) | `musl` (musl libc) | System ABI |
| **Wheel Installation** | 100% pre-compiled wheels | 100% pre-compiled wheels | Build stability |
| **Fargate 512 MB Headroom** | ~335 MB free memory | ~404 MB free memory | Concurrency headroom |

---

## 3. Engineering Trade-Offs

### Debian (slim)

- **Strengths:** Maximum compatibility with Python ecosystem wheels (`manylinux` standard). Relies on `glibc`, the industry standard across enterprise Linux distributions. Zero risk of unexpected runtime discrepancies with network sockets, DNS resolution, or SSL negotiation.
- **Trade-offs:** Base image footprint is larger (~45 MB compressed for base OS vs ~18 MB for Alpine).

### Alpine

- **Strengths:** Meets the sub-60 MB target at **51.72 MB compressed**. Faster image pull times across networks and a 39% smaller uncompressed disk/memory footprint.
- **Trade-offs:** Uses `musl libc`. While the current dependencies (`boto3`, `feedparser`, `requests`) provide pre-compiled `musllinux` wheels, future dependencies with native C extensions may occasionally require compilation tooling (`gcc`, `musl-dev`) during image builds.

---

## 4. Build and Inspection Commands

All commands can be executed via Podman or Docker.

### Building Variants

```bash
# Build Debian slim variant
podman build -t extractor:test -f docs/docker/Dockerfile.slim .

# Build Alpine variant
podman build -t extractor:alpine -f docs/docker/Dockerfile.alpine .
```

### Inspecting Sizes

```bash
# Uncompressed footprint
podman image inspect extractor:test --format '{{.Size}}' | awk '{printf "Slim Uncompressed: %.2f MB\n", $1/1024/1024}'
podman image inspect extractor:alpine --format '{{.Size}}' | awk '{printf "Alpine Uncompressed: %.2f MB\n", $1/1024/1024}'

# Compressed ECR storage footprint
podman save extractor:test | gzip | wc -c | awk '{printf "Slim Compressed ECR: %.2f MB\n", $1/1024/1024}'
podman save extractor:alpine | gzip | wc -c | awk '{printf "Alpine Compressed ECR: %.2f MB\n", $1/1024/1024}'
```

### Local Execution & Verification

```bash
# Run container locally with fallback to local feeds.json
podman run --rm extractor:test
podman run --rm extractor:alpine
```
