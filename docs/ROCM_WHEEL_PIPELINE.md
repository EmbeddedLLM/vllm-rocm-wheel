# vLLM ROCm Wheel Release Pipeline Explained

## Overview

The pipeline builds and releases ROCm-compatible wheels for vLLM and its dependencies. The goal is to allow users to install with:

```bash
pip install vllm --extra-index-url https://vllm-wheels.s3.amazonaws.com/rocm/nightly/
```

---

## Pipeline Flow (Buildkite)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          release-pipeline.yaml                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Job 1: Build ROCm Base Wheels (with S3 caching)                            │
│  ├── Generates cache key from Dockerfile.rocm_base + build args             │
│  ├── Checks S3 cache: s3://bucket/rocm/cache/{cache_key}/                   │
│  │   ├── CACHE HIT:  Download cached wheels, skip Docker build (~2 min)    │
│  │   └── CACHE MISS: Build wheels, upload to cache (~2-3 hours)            │
│  ├── Builds: torch, triton, triton-kernels, torchvision, torchaudio,       │
│  │           amdsmi, flash-attn, aiter                                      │
│  ├── Uses: Dockerfile.rocm_base                                             │
│  ├── Output: rocm-base-image.tar.gz (Docker image with wheels)              │
│  └── Artifacts: artifacts/rocm-base-wheels/*.whl                            │
│                                                                             │
│                              ↓ depends on                                   │
│                                                                             │
│  Job 2: Build vLLM ROCm Wheel                                               │
│  ├── Downloads base wheels + Docker image from S3 (cache or build)          │
│  ├── Uses: Dockerfile.rocm                                                  │
│  ├── Pins dependencies to exact versions from Job 1                         │
│  └── Output: vllm-0.12.0+rocm710-*.whl                                      │
│                                                                             │
│                              ↓ depends on                                   │
│                                                                             │
│  Job 3: Upload ROCm Wheels                                                  │
│  ├── Collects all wheels from Job 1 & 2                                     │
│  ├── Renames linux → manylinux_2_28                                         │
│  ├── Uploads to S3: s3://bucket/rocm/{commit}/                              │
│  ├── Generates PyPI-compatible index (index.html)                           │
│  └── Copies index to: rocm/nightly/, rocm/{version}/                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## S3 Caching for Base Wheels

Job 1 implements S3-based caching to avoid rebuilding base wheels when `Dockerfile.rocm_base` hasn't changed.

### Cache Key Generation

The cache key is generated from:
1. **SHA256 hash of `Dockerfile.rocm_base`** (first 16 characters)
2. **Build arguments hash**: `ROCM_VERSION`, `PYTHON_VERSION`, `PYTORCH_BRANCH`, `TRITON_BRANCH`

```bash
# Example cache key
a1b2c3d4e5f6g7h8-i9j0k1l2
│                  │
└── Dockerfile     └── Build args
    hash               hash
```

### Cache Flow

```
Build #1 (cache MISS):
├── Generate hash: a1b2c3d4...
├── Check S3: s3://bucket/rocm/cache/a1b2c3d4.../  → NOT FOUND
├── Build wheels (~2-3 hours)
├── Upload wheels + Docker image to cache
└── Continue to Job 2

Build #2, #3, #4... (cache HIT):
├── Generate hash: a1b2c3d4...  (same Dockerfile, same args)
├── Check S3: s3://bucket/rocm/cache/a1b2c3d4.../  → FOUND
├── Download cached wheels (~2-3 minutes)
├── Skip Docker build entirely
└── Continue to Job 2

Build #N (Dockerfile changed, cache MISS):
├── Generate hash: x9y8z7w6...  (different hash)
├── Check S3: s3://bucket/rocm/cache/x9y8z7w6.../  → NOT FOUND
├── Build wheels (~2-3 hours)
├── Upload to new cache location
└── Continue to Job 2
```

### Cache Structure in S3

```
s3://vllm-wheels/
└── rocm/
    └── cache/
        └── {cache_key}/
            ├── torch-2.9.0a0+*.whl
            ├── triton-3.4.0-*.whl
            ├── triton_kernels-1.0.0-*.whl
            ├── torchvision-*.whl
            ├── torchaudio-*.whl
            ├── amdsmi-*.whl
            ├── flash_attn-*.whl
            ├── aiter-*.whl
            └── rocm-base-image.tar.gz   ← Docker image also cached
```

### Force Rebuild (Bypass Cache)

To force a fresh build even when cache exists:

**Option 1: Set environment variable in Buildkite UI**
```
ROCM_FORCE_REBUILD=true
```

**Option 2: Set via meta-data**
```bash
buildkite-agent meta-data set "rocm-force-rebuild" "true"
```

### Cache Helper Script

The caching logic is implemented in `.buildkite/scripts/cache-rocm-base-wheels.sh`:

```bash
# Check if cache exists
.buildkite/scripts/cache-rocm-base-wheels.sh check   # outputs "hit" or "miss"

# Download cached wheels
.buildkite/scripts/cache-rocm-base-wheels.sh download

# Upload wheels to cache
.buildkite/scripts/cache-rocm-base-wheels.sh upload

# Get cache key
.buildkite/scripts/cache-rocm-base-wheels.sh key     # outputs cache key

# Get full S3 cache path
.buildkite/scripts/cache-rocm-base-wheels.sh path    # outputs s3://...
```

---

## Job 1: Dockerfile.rocm_base

This builds all the base dependencies as wheels.

```dockerfile
# ============ Stage Structure ============
#
# base (ROCm base image)
#   ├── build_triton      → triton-3.4.0-*.whl, triton_kernels-1.0.0-*.whl
#   ├── build_amdsmi      → amdsmi-*.whl
#   ├── build_pytorch     → torch-2.9.0a0+git*-*.whl
#   ├── build_torchvision → torchvision-*.whl
#   ├── build_torchaudio  → torchaudio-*.whl
#   ├── build_flash_attn  → flash_attn-*.whl
#   └── build_aiter       → aiter-*.whl
#           ↓
#       final stage
#           └── /install/*.whl (all wheels collected)
```

### Key Build Stages:

**1. Triton + Triton Kernels**
```dockerfile
FROM base AS build_triton
ARG TRITON_BRANCH
RUN git clone https://github.com/triton-lang/triton.git \
    && cd triton && git checkout ${TRITON_BRANCH} \
    && python3 setup.py bdist_wheel --dist-dir=dist
# Also builds triton_kernels if present in triton repo
RUN if [ -d triton/python/triton_kernels ]; then \
    cd triton/python/triton_kernels && python3 -m build --wheel; fi
```

**2. PyTorch**
```dockerfile
FROM base AS build_pytorch
ARG PYTORCH_BRANCH
RUN git clone https://github.com/pytorch/pytorch.git \
    && cd pytorch && git checkout ${PYTORCH_BRANCH} \
    && python3 setup.py bdist_wheel
```

**3. Flash Attention**
```dockerfile
FROM base AS build_flash_attn
RUN git clone https://github.com/ROCm/flash-attention.git \
    && cd flash-attention && python3 setup.py bdist_wheel
```

**4. Final Stage - Collect All Wheels**
```dockerfile
FROM base AS final
COPY --from=build_triton /app/install/*.whl /install/
COPY --from=build_pytorch /app/install/*.whl /install/
COPY --from=build_amdsmi /app/install/*.whl /install/
COPY --from=build_torchvision /app/install/*.whl /install/
COPY --from=build_torchaudio /app/install/*.whl /install/
COPY --from=build_flash_attn /app/install/*.whl /install/
COPY --from=build_aiter /app/install/*.whl /install/
# Result: /install/ contains all dependency wheels
```

---

## Job 2: Dockerfile.rocm

This builds the vLLM wheel itself, using the base wheels from Job 1.

```dockerfile
# ============ Key Steps ============

# 1. Start from the base image (has all wheels in /install/)
FROM rocm/vllm-dev:base AS build

# 2. Install the pre-built wheels
RUN pip install /install/*.whl

# 3. Pin exact versions in vLLM's requirements
#    This ensures vLLM's wheel metadata lists exact versions
COPY tools/vllm-rocm/pin_rocm_dependencies.py /tmp/
RUN python3 /tmp/pin_rocm_dependencies.py /install requirements/rocm.txt
```

### What pin_rocm_dependencies.py Does:

```python
# Before (requirements/rocm.txt):
torch>=2.5.0
triton>=3.0.0

# After pinning:
# Custom ROCm wheel pins (auto-generated)
torch==2.9.0a0+git1c57644
triton==3.4.0
triton-kernels==1.0.0
torchvision==0.23.0a0+824e8c8
...

torch>=2.5.0  # (removed or ignored)
triton>=3.0.0  # (removed or ignored)
```

This ensures when you `pip install vllm`, it requires the **exact** versions of the custom ROCm wheels.

**4. Build vLLM Wheel**
```dockerfile
RUN python3 setup.py bdist_wheel
# Output: dist/vllm-0.12.0+rocm710-cp312-cp312-linux_x86_64.whl
```

---

## Job 3: Upload Script (upload-rocm-wheels.sh)

### Step 1: Collect Wheels
```bash
mkdir -p all-rocm-wheels
cp artifacts/rocm-base-wheels/*.whl all-rocm-wheels/
cp artifacts/rocm-vllm-wheel/*.whl all-rocm-wheels/
```

### Step 2: Rename to manylinux
```bash
# linux_x86_64 → manylinux_2_28_x86_64
for wheel in all-rocm-wheels/*.whl; do
    new_wheel="${wheel/linux/manylinux_2_28}"
    mv "$wheel" "$new_wheel"
done
```

### Step 3: Upload to S3
```bash
for wheel in all-rocm-wheels/*.whl; do
    aws s3 cp "$wheel" "s3://bucket/rocm/${COMMIT}/"
done
```

### Step 4: Generate PyPI Index
```bash
python3 generate-nightly-index.py \
    --version "rocm/${COMMIT}" \
    --current-objects objects.json \
    --output-dir rocm-indices/
```

### Step 5: Upload Index to Multiple Locations
```bash
# Per-commit (always)
aws s3 cp --recursive rocm-indices/ s3://bucket/rocm/${COMMIT}/

# Nightly (if main branch)
aws s3 cp --recursive rocm-indices/ s3://bucket/rocm/nightly/

# Version-specific (if not dev)
aws s3 cp --recursive rocm-indices/ s3://bucket/rocm/0.12.0/
```

---

## S3 Structure

```
s3://vllm-wheels/
└── rocm/
    ├── {commit-hash}/                    ← Wheels stored here
    │   ├── vllm-0.12.0+rocm710-*.whl
    │   ├── torch-2.9.0a0+git*-*.whl
    │   ├── triton-3.4.0-*.whl
    │   ├── triton_kernels-1.0.0-*.whl
    │   └── ... (other wheels)
    │
    ├── {commit-hash}/                    ← Index for this commit
    │   ├── index.html                    ← Lists: rocm710/
    │   └── rocm710/
    │       ├── index.html                ← Lists: vllm/, torch/, triton/, ...
    │       ├── vllm/index.html           ← Links to vllm wheel
    │       ├── torch/index.html          ← Links to torch wheel
    │       ├── triton/index.html
    │       └── triton-kernels/index.html ← Normalized name (PEP 503)
    │
    ├── nightly/                          ← Index copied here (same structure)
    │   └── rocm710/...
    │
    └── 0.12.0/                           ← Index copied here (release version)
        └── rocm710/...
```

---

## Index HTML Format (PEP 503)

**Root index.html** (lists variants):
```html
<!DOCTYPE html>
<html>
  <meta name="pypi:repository-version" content="1.0">
  <body>
    <a href="rocm710/">rocm710/</a><br/>
  </body>
</html>
```

**Variant index.html** (lists packages):
```html
<!DOCTYPE html>
<html>
  <body>
    <a href="vllm/">vllm/</a><br/>
    <a href="torch/">torch/</a><br/>
    <a href="triton/">triton/</a><br/>
    <a href="triton-kernels/">triton-kernels/</a><br/>
    ...
  </body>
</html>
```

**Package index.html** (links to wheels):
```html
<!DOCTYPE html>
<html>
  <body>
    <a href="../../../{commit}/vllm-0.12.0%2Brocm710-cp312-cp312-manylinux_2_28_x86_64.whl">
      vllm-0.12.0+rocm710-cp312-cp312-manylinux_2_28_x86_64.whl
    </a><br/>
  </body>
</html>
```

---

## How pip Install Works

```bash
pip install vllm --extra-index-url https://bucket.s3.amazonaws.com/rocm/nightly/rocm710/
```

1. **pip checks PyPI first** → finds `vllm-0.12.0` (CUDA version)
2. **pip checks extra-index** → finds `vllm-0.12.0+rocm710`
3. **pip resolves dependencies** from vllm's metadata:
   - `torch==2.9.0a0+git1c57644` → found in extra-index ✓
   - `triton==3.4.0` → found in extra-index ✓
   - `triton-kernels==1.0.0` → found in extra-index (via `triton-kernels/`) ✓
4. **pip downloads all wheels** from S3
5. **pip installs** the complete ROCm stack

---

## Key Files Summary

| File | Purpose |
|------|---------|
| `release-pipeline.yaml` | Buildkite pipeline orchestration |
| `Dockerfile.rocm_base` | Builds torch, triton, flash-attn, etc. |
| `Dockerfile.rocm` | Builds vLLM wheel with pinned deps |
| `pin_rocm_dependencies.py` | Pins exact versions in requirements |
| `generate-nightly-index.py` | Creates PyPI-compatible index.html |
| `upload-rocm-wheels.sh` | Uploads wheels and indices to S3 |

---

## Troubleshooting

### pip falls back to PyPI version
- Use `--index-url` (primary) instead of `--extra-index-url` (secondary)
- Pin exact version: `pip install vllm==0.12.0+rocm710`

### Package not found (e.g., triton-kernels)
- Check package name normalization (PEP 503): `triton_kernels` → `triton-kernels/`
- Verify index.html lists the package directory

### Wrong wheel version installed
- Check `pin_rocm_dependencies.py` ran correctly during build
- Verify wheel metadata: `unzip -p vllm-*.whl '*/METADATA' | grep Requires-Dist`

### Permission denied on build agent
- Docker creates files as root; buildkite-agent can't delete them
- Fix: `sudo rm -rf /var/lib/buildkite-agent/builds/...`
