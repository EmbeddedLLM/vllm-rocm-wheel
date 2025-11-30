# Adding Custom Packages to the ROCm Wheel Pipeline

**Last Updated**: November 2025

This guide explains how to add new custom-built packages (like torchaudio, mori, etc.) to the vLLM ROCm wheel build pipeline.

## Table of Contents

- [Introduction](#introduction)
- [Quick Reference](#quick-reference)
- [Files to Modify](#files-to-modify)
- [Step-by-Step Guide](#step-by-step-guide)
- [Examples](#examples)
- [Architecture Considerations](#architecture-considerations)
- [Troubleshooting](#troubleshooting)
- [Pipeline Architecture](#pipeline-architecture)

## Introduction

### What are Custom Packages?

Custom packages are ROCm-optimized versions of PyTorch ecosystem packages that we build from source instead of using the standard PyPI versions. These custom builds:

- Are optimized for specific AMD GPUs (gfx90a, gfx942, gfx950, etc.)
- Include ROCm-specific patches and optimizations
- Ensure compatibility across the entire stack (PyTorch, Triton, vLLM)

### Currently Supported Custom Packages

The pipeline currently builds these custom packages:

1. **torch** - Core PyTorch with ROCm support
2. **triton** + **triton_kernels** - GPU kernel compiler
3. **torchvision** - Computer vision utilities
4. **amdsmi** - AMD System Management Interface
5. **flash-attn** - Fast attention implementation
6. **aiter** - Async iterator utilities (gfx942/gfx950 only)

### Why Add Custom Packages?

You might add a custom package when:
- A package needs ROCm-specific optimizations
- PyPI versions don't support your target GPU architectures
- You need specific patches or versions not available on PyPI
- You want to ensure compatibility with your custom PyTorch build

## Quick Reference

### Files Checklist

When adding a new custom package (e.g., `torchaudio`), modify these files:

- [ ] `docker/Dockerfile.rocm_base` - Add ARG declarations
- [ ] `docker/Dockerfile.rocm_base` - Create build stage
- [ ] `docker/Dockerfile.rocm_base` - Add to `debs` stage
- [ ] `docker/Dockerfile.rocm_base` - Add to `versions.txt`
- [ ] `tools/vllm-rocm/pin_rocm_dependencies.py` - Add to package mapping
- [ ] `tools/vllm-rocm/cleanup_pypi_duplicates.sh` - Add to packages list
- [ ] Test the build locally or in CI

### Files That DON'T Need Changes

These files automatically adapt:
- `docker/Dockerfile.rocm` - Dynamically scans `/install` for wheels
- `.github/workflows/build-rocm-wheel.yml` - No changes needed
- All other pipeline scripts - Work automatically

## Files to Modify

### 1. `docker/Dockerfile.rocm_base`

This is the main file where you define how to build your custom package.

**Modifications needed:**
1. Add ARG declarations (top of file)
2. Create a build stage
3. Add to the `debs` collection stage
4. Add to `versions.txt` recording

### 2. `tools/vllm-rocm/pin_rocm_dependencies.py`

This script pins custom wheel versions in vLLM's requirements.

**Modification needed:**
- Add your package to the `package_mapping` dictionary (around line 52-60)

### 3. `tools/vllm-rocm/cleanup_pypi_duplicates.sh`

This script removes PyPI versions of custom packages to avoid conflicts.

**Modification needed:**
- Add your package to the `PACKAGES_TO_CHECK` array (around line 131)

## Step-by-Step Guide

### Step 1: Add ARG Declarations

Add these at the top of `docker/Dockerfile.rocm_base` (after existing ARGs):

```dockerfile
ARG TORCHAUDIO_BRANCH="v2.5.0"
ARG TORCHAUDIO_REPO="https://github.com/pytorch/audio.git"
```

**Why**: These define which version/repo to build from. They can be overridden at build time.

### Step 2: Create Build Stage

Add a new build stage in `docker/Dockerfile.rocm_base` (after existing build stages, before `debs` stage):

```dockerfile
FROM base AS build_torchaudio
ARG TORCHAUDIO_BRANCH
ARG TORCHAUDIO_REPO
# Install dependencies (torch) from previous build stage
RUN --mount=type=bind,from=build_pytorch,src=/app/install/,target=/install \
    pip install /install/*.whl
# Clone and build the package
RUN git clone ${TORCHAUDIO_REPO} torchaudio \
    && cd torchaudio \
    && git checkout ${TORCHAUDIO_BRANCH} \
    && git submodule update --init --recursive \
    && python3 setup.py bdist_wheel --dist-dir=dist
# Copy wheel to /app/install for collection
RUN mkdir -p /app/install && cp /app/torchaudio/dist/*.whl /app/install
```

**Key points:**
- Stage name: `build_<package_name>`
- Use `--mount=type=bind` to access wheels from dependency stages
- Install dependencies before building (e.g., torchaudio needs torch)
- Output wheels to `/app/install`

#### Architecture-Specific Builds

If your package only supports certain GPU architectures:

```dockerfile
FROM base AS build_torchaudio
ARG TORCHAUDIO_BRANCH
ARG TORCHAUDIO_REPO
# Define architecture limitation
ENV TORCHAUDIO_ROCM_ARCH=gfx942;gfx950
RUN --mount=type=bind,from=build_pytorch,src=/app/install/,target=/install \
    pip install /install/*.whl
RUN git clone ${TORCHAUDIO_REPO} torchaudio \
    && cd torchaudio \
    && git checkout ${TORCHAUDIO_BRANCH} \
    && GPU_ARCHS=${TORCHAUDIO_ROCM_ARCH} python3 setup.py bdist_wheel --dist-dir=dist
RUN mkdir -p /app/install && cp /app/torchaudio/dist/*.whl /app/install
```

### Step 3: Add to `debs` Collection Stage

In the `debs` stage, add a line to copy your wheels:

```dockerfile
FROM base AS debs
RUN mkdir /app/debs
# ... existing COPY commands ...
RUN --mount=type=bind,from=build_torchaudio,src=/app/install/,target=/install \
    cp /install/*.whl /app/debs
```

**Why**: This collects all custom wheels into one place for the final image.

### Step 4: Add to Version Recording

In the `final` stage, add your package info to `versions.txt`:

```dockerfile
ARG BASE_IMAGE
ARG TRITON_BRANCH
# ... existing ARGs ...
ARG TORCHAUDIO_BRANCH
ARG TORCHAUDIO_REPO
RUN echo "BASE_IMAGE: ${BASE_IMAGE}" > /app/versions.txt \
    && echo "TRITON_BRANCH: ${TRITON_BRANCH}" >> /app/versions.txt \
    # ... existing echo commands ...
    && echo "TORCHAUDIO_BRANCH: ${TORCHAUDIO_BRANCH}" >> /app/versions.txt \
    && echo "TORCHAUDIO_REPO: ${TORCHAUDIO_REPO}" >> /app/versions.txt
```

**Why**: This records which version was built for debugging and reproducibility.

### Step 5: Update Pin Script

In `tools/vllm-rocm/pin_rocm_dependencies.py`, add your package to the mapping:

```python
package_mapping = {
    'torch-': 'torch',
    'triton-': 'triton',
    'triton_kernels-': 'triton-kernels',
    'torchvision-': 'torchvision',
    'amdsmi-': 'amdsmi',
    'flash_attn-': 'flash-attn',
    'aiter-': 'aiter',
    'torchaudio-': 'torchaudio',  # ADD THIS LINE
}
```

**Key points:**
- Use the wheel filename prefix with dash (e.g., `torchaudio-`)
- Use the requirements.txt name (may use dashes, not underscores)
- This handles wheel filename to package name conversion

### Step 6: Update Cleanup Script

In `tools/vllm-rocm/cleanup_pypi_duplicates.sh`, add your package:

```bash
PACKAGES_TO_CHECK=("torch" "triton" "torchvision" "amdsmi" "flash-attn" "aiter" "torchaudio")
```

**Why**: This ensures PyPI versions of your package are removed, keeping only your custom build.

### Step 7: Test Your Build

Test locally or via CI:

```bash
# Build the base image
docker buildx build \
  --file docker/Dockerfile.rocm_base \
  --tag rocm/vllm-dev:base \
  --build-arg PYTORCH_ROCM_ARCH="gfx942" \
  --build-arg PYTHON_VERSION="3.12" \
  --load \
  .

# Extract wheels to verify
mkdir -p test-wheels
container_id=$(docker create rocm/vllm-dev:base)
docker cp ${container_id}:/install/. test-wheels/
docker rm ${container_id}

# Check that your wheel exists
ls -lh test-wheels/torchaudio*.whl
```

## Examples

### Example 1: Simple Package (torchaudio)

**Characteristics:**
- Standard PyTorch package
- Depends on torch
- Builds for all architectures
- Standard setup.py build

**Full implementation:**

```dockerfile
# 1. ARG declarations
ARG TORCHAUDIO_BRANCH="v2.5.0"
ARG TORCHAUDIO_REPO="https://github.com/pytorch/audio.git"

# 2. Build stage
FROM base AS build_torchaudio
ARG TORCHAUDIO_BRANCH
ARG TORCHAUDIO_REPO
RUN --mount=type=bind,from=build_pytorch,src=/app/install/,target=/install \
    pip install /install/*.whl
RUN git clone ${TORCHAUDIO_REPO} torchaudio \
    && cd torchaudio \
    && git checkout ${TORCHAUDIO_BRANCH} \
    && git submodule update --init --recursive \
    && python3 setup.py bdist_wheel --dist-dir=dist
RUN mkdir -p /app/install && cp /app/torchaudio/dist/*.whl /app/install

# 3. Collection stage
FROM base AS debs
# ... existing stages ...
RUN --mount=type=bind,from=build_torchaudio,src=/app/install/,target=/install \
    cp /install/*.whl /app/debs

# 4. Version recording
ARG TORCHAUDIO_BRANCH
ARG TORCHAUDIO_REPO
RUN echo "TORCHAUDIO_BRANCH: ${TORCHAUDIO_BRANCH}" >> /app/versions.txt \
    && echo "TORCHAUDIO_REPO: ${TORCHAUDIO_REPO}" >> /app/versions.txt
```

**Script updates:**

```python
# pin_rocm_dependencies.py
'torchaudio-': 'torchaudio',
```

```bash
# cleanup_pypi_duplicates.sh
PACKAGES_TO_CHECK=("torch" "triton" "torchvision" "amdsmi" "flash-attn" "aiter" "torchaudio")
```

### Example 2: Architecture-Limited Package (aiter)

**Characteristics:**
- Only supports gfx942 and gfx950
- Custom build environment variable (GPU_ARCHS)
- Requires additional dependencies (pyyaml)

**Full implementation:**

```dockerfile
# 1. ARG declarations
ARG AITER_BRANCH="59bd8ff2"
ARG AITER_REPO="https://github.com/ROCm/aiter.git"

# 2. Build stage with architecture limitation
FROM base AS build_aiter
ARG AITER_BRANCH
ARG AITER_REPO
ENV AITER_ROCM_ARCH=gfx942;gfx950
RUN --mount=type=bind,from=build_pytorch,src=/app/install/,target=/install \
    pip install /install/*.whl
RUN git clone --recursive ${AITER_REPO} aiter \
    && cd aiter \
    && git checkout ${AITER_BRANCH} \
    && git submodule update --init --recursive \
    && pip install -r requirements.txt
RUN pip install pyyaml \
    && cd aiter \
    && GPU_ARCHS=${AITER_ROCM_ARCH} python3 setup.py bdist_wheel --dist-dir=dist
RUN mkdir -p /app/install && cp /app/aiter/dist/*.whl /app/install

# 3. Collection stage
RUN --mount=type=bind,from=build_aiter,src=/app/install/,target=/install \
    cp /install/*.whl /app/debs

# 4. Version recording
ARG AITER_BRANCH
ARG AITER_REPO
RUN echo "AITER_BRANCH: ${AITER_BRANCH}" >> /app/versions.txt \
    && echo "AITER_REPO: ${AITER_REPO}" >> /app/versions.txt
```

**Script updates:**

```python
# pin_rocm_dependencies.py
'aiter-': 'aiter',
```

```bash
# cleanup_pypi_duplicates.sh
PACKAGES_TO_CHECK=("torch" "triton" "torchvision" "amdsmi" "flash-attn" "aiter")
```

### Example 3: Package Template

Use this as a starting point for any new package:

```dockerfile
# === ADD TO TOP OF FILE ===
ARG PACKAGE_BRANCH="v1.0.0"
ARG PACKAGE_REPO="https://github.com/org/package.git"

# === ADD BEFORE 'debs' STAGE ===
FROM base AS build_package
ARG PACKAGE_BRANCH
ARG PACKAGE_REPO
# Install dependencies if needed
RUN --mount=type=bind,from=build_pytorch,src=/app/install/,target=/install \
    pip install /install/*.whl
# Clone and build
RUN git clone ${PACKAGE_REPO} package \
    && cd package \
    && git checkout ${PACKAGE_BRANCH} \
    && git submodule update --init --recursive \
    && pip install -r requirements.txt || true \
    && python3 setup.py bdist_wheel --dist-dir=dist
# Copy to /app/install
RUN mkdir -p /app/install && cp /app/package/dist/*.whl /app/install

# === ADD TO 'debs' STAGE ===
RUN --mount=type=bind,from=build_package,src=/app/install/,target=/install \
    cp /install/*.whl /app/debs

# === ADD TO 'final' STAGE ===
ARG PACKAGE_BRANCH
ARG PACKAGE_REPO
RUN echo "PACKAGE_BRANCH: ${PACKAGE_BRANCH}" >> /app/versions.txt \
    && echo "PACKAGE_REPO: ${PACKAGE_REPO}" >> /app/versions.txt
```

**Script updates:**

```python
# pin_rocm_dependencies.py - add this line
'package_name-': 'package-name',  # wheel prefix -> requirements.txt name
```

```bash
# cleanup_pypi_duplicates.sh - add to array
PACKAGES_TO_CHECK=("torch" "triton" "torchvision" "amdsmi" "flash-attn" "aiter" "package-name")
```

## Architecture Considerations

### GPU Architecture Support

The `PYTORCH_ROCM_ARCH` environment variable (defined in `base` stage) specifies which GPU architectures to build for:

```dockerfile
ARG PYTORCH_ROCM_ARCH=gfx90a;gfx942;gfx950;gfx1100;gfx1101;gfx1200;gfx1201;gfx1150;gfx1151
ENV PYTORCH_ROCM_ARCH=${PYTORCH_ROCM_ARCH}
```

**Common architectures:**
- `gfx90a` - MI210, MI250 series
- `gfx942` - MI300A, MI300X
- `gfx950` - Next-generation MI300 series
- `gfx1100`, `gfx1101`, `gfx1200`, `gfx1201` - Consumer GPUs (RX 7000 series)

### Limiting Package to Specific Architectures

Some packages may not support all architectures. Use a separate environment variable:

```dockerfile
FROM base AS build_mypackage
ENV MYPACKAGE_ROCM_ARCH=gfx942;gfx950  # Only build for these
RUN cd mypackage && GPU_ARCHS=${MYPACKAGE_ROCM_ARCH} python3 setup.py bdist_wheel
```

### Build Dependencies

Use `--mount=type=bind` to access wheels from previous stages:

```dockerfile
# If your package depends on torch
RUN --mount=type=bind,from=build_pytorch,src=/app/install/,target=/install \
    pip install /install/*.whl

# If your package depends on both torch and flash-attn
RUN --mount=type=bind,from=build_pytorch,src=/app/install/,target=/pytorch \
    --mount=type=bind,from=build_fa,src=/app/install/,target=/fa \
    pip install /pytorch/*.whl /fa/*.whl
```

**Build order matters!** Your stage's `from=build_X` must reference stages that appear earlier in the Dockerfile.

### Build Flags and Environment Variables

Common build customizations:

```dockerfile
# Set compiler flags
ENV CC=clang
ENV CXX=clang++

# Set ROCm path
ENV ROCM_PATH=/opt/rocm

# Pass custom build flags
RUN cd package && GPU_ARCHS=${ARCH} MAX_JOBS=8 python3 setup.py bdist_wheel

# Use specific Python build backend
RUN cd package && python3 -m build --wheel
```

## Troubleshooting

### Issue: Package not pinned in vLLM requirements

**Symptom:** vLLM builds with PyPI version instead of custom wheel

**Solution:** Check that you updated `pin_rocm_dependencies.py`:
```python
# Verify the package mapping exists
'your_package-': 'your-package',
```

**Debug:**
```bash
# Check what's in /install
docker run --rm rocm/vllm-dev:base ls -lh /install/

# Check vLLM's requirements after pinning
docker run --rm rocm/vllm-dev:base cat /app/vllm/requirements/rocm.txt | head -20
```

### Issue: PyPI duplicate not removed

**Symptom:** Both custom and PyPI versions in final wheels

**Solution:** Verify `cleanup_pypi_duplicates.sh` includes your package:
```bash
PACKAGES_TO_CHECK=("torch" "triton" "torchvision" "amdsmi" "flash-attn" "aiter" "your-package")
```

**Debug:**
```bash
# Check which versions exist
ls all-wheels/your_package*.whl

# Run cleanup script manually
bash tools/vllm-rocm/cleanup_pypi_duplicates.sh artifacts/rocm-base-wheels all-wheels
```

### Issue: Build fails with "wheel not found"

**Symptom:** `cp: cannot stat '/app/package/dist/*.whl': No such file or directory`

**Possible causes:**
1. Build failed silently - check build logs
2. Wheel output path is different
3. Package uses different build system

**Solutions:**
```dockerfile
# Add error checking
RUN cd package && python3 setup.py bdist_wheel --dist-dir=dist \
    && ls -lh dist/*.whl  # Verify wheel was created

# Try different output location
RUN cd package && python3 -m build --wheel  # Output to dist/
RUN cd package && pip wheel . --wheel-dir=dist/  # Alternative method
```

### Issue: Architecture compatibility errors

**Symptom:** Build succeeds but fails to run on target GPU

**Solution:** Verify GPU_ARCHS is set correctly:
```dockerfile
# Check what architectures were built
RUN cd package && GPU_ARCHS=${YOUR_ROCM_ARCH} python3 setup.py bdist_wheel 2>&1 | grep -i "arch"

# Or inspect the wheel metadata
RUN unzip -p /app/install/package*.whl "*.dist-info/WHEEL"
```

### Issue: Missing dependencies during build

**Symptom:** `ImportError` or `ModuleNotFoundError` during wheel build

**Solution:** Install build dependencies:
```dockerfile
# Install from requirements.txt
RUN cd package && pip install -r requirements.txt

# Install specific dependencies
RUN pip install pyyaml cmake ninja

# Use build isolation (installs build deps automatically)
RUN pip install build && cd package && python3 -m build --wheel
```

## Pipeline Architecture

### Overview

The pipeline follows this flow:

```
┌─────────────────────────────────────────────────────────────┐
│                    Dockerfile.rocm_base                     │
│  Builds custom wheels: torch, triton, flash-attn, etc.     │
│  Output: /install/*.whl                                     │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    Dockerfile.rocm                          │
│  1. Pins custom wheels in requirements (pin_rocm_deps.py)  │
│  2. Builds vLLM wheel with pinned dependencies             │
│  3. Collects all dependency wheels                          │
│  4. Filters custom wheels from dependencies                 │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              GitHub Actions Workflow                         │
│  1. Extracts wheels from Docker images                      │
│  2. Removes PyPI duplicates (cleanup_pypi_duplicates.sh)    │
│  3. Generates PyPI index (generate_s3_index.py)             │
│  4. Uploads to S3 (upload_to_s3.sh)                         │
└─────────────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                   S3 PyPI Repository                         │
│  Users can: pip install vllm --index-url <S3-URL>           │
└─────────────────────────────────────────────────────────────┘
```

### Key Scripts

1. **`pin_rocm_dependencies.py`**
   - **Purpose:** Ensures vLLM uses custom wheels
   - **Input:** Scans `/install/*.whl` for custom packages
   - **Output:** Modifies `requirements/rocm.txt` with exact versions
   - **When:** During vLLM build in Dockerfile.rocm

2. **`filter_system_packages.py`**
   - **Purpose:** Removes system packages from dependencies
   - **Input:** pipdeptree output
   - **Output:** Filtered dependency list
   - **When:** After collecting vLLM dependencies

3. **`cleanup_pypi_duplicates.sh`**
   - **Purpose:** Removes PyPI versions of custom packages
   - **Input:** Base wheels directory + all wheels directory
   - **Output:** Cleaned wheel collection (only custom versions)
   - **When:** In GitHub Actions before upload

4. **`generate_s3_index.py`**
   - **Purpose:** Creates PyPI-compatible index
   - **Input:** Wheel directory
   - **Output:** HTML index files (simple/ directory structure)
   - **When:** In GitHub Actions before upload

5. **`upload_to_s3.sh`**
   - **Purpose:** Syncs wheels and index to S3
   - **Input:** Wheels directory + index directory
   - **Output:** S3 bucket populated
   - **When:** Final step in GitHub Actions

### Automatic vs. Manual Updates

**Automatically handles:**
- Scanning `/install` for any custom wheels
- Filtering custom wheels from dependency collection
- Generating index for all wheels found
- Uploading all wheels to S3

**Requires manual updates:**
- Package name mapping (pin_rocm_dependencies.py)
- Duplicate detection (cleanup_pypi_duplicates.sh)

**Why manual updates needed?** Wheel filenames use underscores (e.g., `flash_attn-`) but requirements.txt uses dashes (e.g., `flash-attn`). The scripts need this mapping to handle the conversion correctly.

### Testing Your Changes

1. **Local Docker build:**
   ```bash
   docker buildx build --file docker/Dockerfile.rocm_base --target debs --load .
   ```

2. **Extract and inspect wheels:**
   ```bash
   container_id=$(docker create <image>)
   docker cp ${container_id}:/app/debs/. test-wheels/
   docker rm ${container_id}
   ls -lh test-wheels/
   ```

3. **Test pinning script:**
   ```bash
   python3 tools/vllm-rocm/pin_rocm_dependencies.py test-wheels/ requirements-test.txt
   cat requirements-test.txt
   ```

4. **Test cleanup script:**
   ```bash
   bash tools/vllm-rocm/cleanup_pypi_duplicates.sh test-wheels/ all-wheels/
   ```

## See Also

- [README.md](./README.md) - Overview of all pipeline scripts
- [../../../docker/Dockerfile.rocm_base](../../../docker/Dockerfile.rocm_base) - Base wheel builds
- [../../../docker/Dockerfile.rocm](../../../docker/Dockerfile.rocm) - vLLM build
- [../../../.github/workflows/build-rocm-wheel.yml](../../../.github/workflows/build-rocm-wheel.yml) - CI/CD workflow
