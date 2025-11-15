# vLLM ROCm PyPI Repository - GitHub Actions Workflow

This workflow builds vLLM ROCm wheels along with all dependencies and publishes them to a GitHub Pages-based PyPI repository.

## Overview

The workflow consists of 4 jobs that run sequentially:

1. **Build Base Wheels** - Builds PyTorch, Triton, and AMDSMI from source
2. **Collect Dependency Wheels** - Downloads all Python dependencies from PyPI
3. **Build vLLM Wheel** - Builds the main vLLM-ROCm wheel
4. **Create PyPI Repository** - Generates a PEP 503 simple repository and publishes to GitHub Pages

## Quick Start

### Trigger the Workflow

1. Go to **Actions** tab in GitHub
2. Select "Build ROCm Wheels and Publish to PyPI"
3. Click "Run workflow"
4. Configure parameters (optional):
   - **ROCm GPU architectures**: `gfx942` (default for MI300)
   - **Python version**: `3.12` (default)
   - **ROCm version**: `7.1` (default)

### Install from Your PyPI Repository

Once the workflow completes, install vLLM with:

```bash
pip install vllm-rocm --index-url https://embeddedllm.github.io/vllm-rocm/simple/
```

## Workflow Details

### Job 1: Build Base Wheels

**What it does:**
- Builds the minimal ROCm base image using `docker/Dockerfile.rocm_base.minimal`
- Compiles PyTorch, Triton, and AMDSMI from source for ROCm
- Extracts `.whl` files from the Docker image
- Uploads wheels as artifacts

**Artifacts produced:**
- `rocm-base-wheels`: Contains PyTorch, torchvision, Triton, and AMDSMI wheels

**Build time:** ~60-90 minutes (single GPU architecture)

### Job 2: Collect Dependency Wheels

**What it does:**
- Parses `requirements/rocm.txt` and `requirements/common.txt`
- Downloads pre-built wheels from PyPI for all dependencies
- For loose version specs (e.g., `>=2.0,<3.0`), downloads multiple versions
- Uploads wheels as artifacts

**Artifacts produced:**
- `dependency-wheels`: Contains all dependency wheels from PyPI

**Build time:** ~5-10 minutes

**Script used:** `.github/scripts/download_dependency_wheels.py`

### Job 3: Build vLLM Wheel

**What it does:**
- Builds the full ROCm base image
- Compiles vLLM with ROCm support inside the container
- Repairs the wheel using `auditwheel` for manylinux compatibility
- Uploads the repaired wheel as artifact

**Artifacts produced:**
- `vllm-wheel`: Contains the manylinux-compatible vLLM wheel

**Build time:** ~30-45 minutes

### Job 4: Create PyPI Repository

**What it does:**
- Downloads all artifacts (base wheels, dependencies, vLLM wheel)
- Generates a PEP 503 simple repository structure using `dumb-pypi`
- Creates an index page with build information
- Commits and pushes to `gh-pages` branch

**Output:**
- GitHub Pages site at: `https://embeddedllm.github.io/vllm-rocm/`
- PyPI simple index at: `https://embeddedllm.github.io/vllm-rocm/simple/`

## Minimal Dockerfile Strategy

The workflow uses `docker/Dockerfile.rocm_base.minimal` for faster iteration.

### What's Included (Minimal)

✅ **Included** (essential components):
- PyTorch ROCm fork
- Triton ROCm fork
- AMDSMI (AMD GPU monitoring)
- Single GPU architecture: `gfx942` (MI300)

### What's Excluded (For Speed)

❌ **Excluded** (to reduce build time):
- Flash Attention (~15 min build time)
- AITER (~10 min build time)
- Multiple GPU architectures (~70% time savings)

### Iterating Faster

**Stage 1: Initial Setup (Current)**
- Build: PyTorch + Triton + AMDSMI
- Architecture: `gfx942` only
- Estimated time: ~60 minutes
- Purpose: Get the pipeline working end-to-end

**Stage 2: Add Capabilities**
Once the pipeline is stable, incrementally add:
1. Flash Attention (optional but recommended for performance)
2. AITER (for async operations)
3. Additional architectures if needed

**Stage 3: Full Build**
- Edit `docker/Dockerfile.rocm_base.minimal` to add excluded stages
- Or switch to using `docker/Dockerfile.rocm_base` (full version)

### Build Time Comparison

| Configuration | Build Time | Components |
|---------------|------------|------------|
| Minimal (current) | ~60 min | PyTorch + Triton + AMDSMI, 1 arch |
| +Flash Attention | ~75 min | Above + Flash Attention |
| +AITER | ~85 min | Above + AITER |
| Full (all archs) | ~180 min | All components, 9 architectures |

## Customization

### Change GPU Architectures

Edit `docker/Dockerfile.rocm_base.minimal:19`:

```dockerfile
# Single architecture (fast)
ARG PYTORCH_ROCM_ARCH=gfx942

# Multiple architectures (slower)
ARG PYTORCH_ROCM_ARCH=gfx942;gfx90a;gfx950
```

Or set via workflow input parameter.

### Add More Components

To add Flash Attention back:

1. Open `docker/Dockerfile.rocm_base.minimal`
2. Copy the `build_fa` stage from `docker/Dockerfile.rocm_base`
3. Add to the `debs` stage:
   ```dockerfile
   RUN --mount=type=bind,from=build_fa,src=/app/install/,target=/install \
       cp /install/*.whl /app/debs
   ```

### Change Python Version

Edit workflow input or change default in `docker/Dockerfile.rocm_base.minimal:26`:

```dockerfile
ARG PYTHON_VERSION=3.12
```

## Troubleshooting

### Build Failures

**Issue:** Docker build times out
- **Solution:** Increase timeout in workflow or split into multiple stages

**Issue:** Out of disk space
- **Solution:** Add cleanup steps between build stages

**Issue:** Wheel incompatibility errors
- **Solution:** Check Python version matches between base image and vLLM build

### Dependency Download Failures

**Issue:** PyPI package not found
- **Solution:** Check if package exists on PyPI or needs alternate index

**Issue:** Too many versions downloaded
- **Solution:** Adjust `--max-versions` parameter in workflow (line 80)

### PyPI Repository Issues

**Issue:** GitHub Pages not updating
- **Solution:** Check repository Settings > Pages > Source is set to "gh-pages" branch

**Issue:** 404 errors when installing
- **Solution:** Verify URL format: `https://embeddedllm.github.io/vllm-rocm/simple/`

## Advanced: Adding Custom Wheels

To include additional custom-built wheels:

1. Build your wheel in a separate job
2. Upload as artifact
3. Modify Job 4 to download and include it:
   ```yaml
   - name: Download custom wheels
     uses: actions/download-artifact@v4
     with:
       name: my-custom-wheel
       path: artifacts/custom
   ```

## File Structure

```
.github/
├── workflows/
│   ├── build-rocm-wheel.yml    # Main workflow
│   └── README.md               # This file
└── scripts/
    └── download_dependency_wheels.py  # Dependency downloader

docker/
├── Dockerfile.rocm_base.minimal  # Minimal base image (fast)
└── Dockerfile.rocm_base          # Full base image (comprehensive)

requirements/
├── rocm.txt      # ROCm-specific dependencies
└── common.txt    # Common dependencies
```

## GitHub Pages Setup

**First-time setup:**

1. Go to repository Settings > Pages
2. Source: Deploy from a branch
3. Branch: `gh-pages` / `(root)`
4. Save

The workflow will automatically create the `gh-pages` branch on first run.

## Monitoring

### Build Progress

- Check Actions tab for real-time logs
- Each job shows detailed progress
- Artifacts available after job completion

### PyPI Repository

- Visit: `https://embeddedllm.github.io/vllm-rocm/`
- Browse packages: `https://embeddedllm.github.io/vllm-rocm/simple/`
- Build info displayed on index page

## CI/CD Integration

### Automatic Builds

To trigger builds automatically:

```yaml
on:
  push:
    branches:
      - main
  schedule:
    - cron: '0 0 * * 0'  # Weekly on Sunday
```

### Testing Before Publish

Add a test job before publishing:

```yaml
test-vllm-wheel:
  needs: build-vllm-wheel
  runs-on: ubuntu-latest
  steps:
    - name: Download vLLM wheel
      uses: actions/download-artifact@v4
    - name: Install and test
      run: |
        pip install artifacts/vllm-wheel/*.whl
        python -c "import vllm; print(vllm.__version__)"
```

## Performance Tips

1. **Use Docker layer caching**: Already enabled via `docker/setup-buildx-action@v3`
2. **Parallel downloads**: The dependency script downloads in parallel
3. **Incremental builds**: Modify only what you need in minimal Dockerfile
4. **Artifact retention**: Set to 7 days to save storage

## Support

For issues with:
- **Workflow**: Check Actions logs and this README
- **vLLM build**: See main repository documentation
- **ROCm**: Consult AMD ROCm documentation

## Version History

- **v1.0** (2025-01-15): Initial release with minimal Dockerfile strategy
