# vLLM ROCm Wheel Build Pipeline Tools

This directory contains scripts for building and publishing vLLM ROCm wheels with custom-built PyTorch, Triton, and other ROCm packages.

**Documentation:**
- **[ADDING_PACKAGES.md](./ADDING_PACKAGES.md)** - Complete guide for adding new custom packages to the pipeline

## Scripts

### Core Pipeline Scripts

- **`pin_rocm_dependencies.py`** - Pins custom ROCm wheels in vLLM requirements
  - Scans `/install` for custom wheels (torch, triton, torchvision, amdsmi, flash-attn, aiter)
  - Inserts exact version pins at the top of `requirements/rocm.txt`
  - Ensures pip installs custom builds instead of PyPI versions

- **`filter_system_packages.py`** - Filters system packages from dependencies
  - Removes system-installed packages from pipdeptree output
  - Prevents attempting to download unavailable packages from PyPI

- **`cleanup_pypi_duplicates.sh`** - Removes PyPI duplicates of custom packages
  - Ensures only custom-built versions are included in final wheel collection
  - Validates vLLM wheel metadata for correct dependency pinning
  - Calls `check_wheel_metadata.py` for validation

- **`check_wheel_metadata.py`** - Validates vLLM wheel metadata
  - Verifies wheel has correct torch/triton dependency pins
  - Used by `cleanup_pypi_duplicates.sh` for duplicate detection

### PyPI Repository Management

- **`generate_s3_index.py`** - Generates PyPI-compatible index for S3
  - Creates `simple/` directory structure with package indices
  - Generates HTML index files compatible with pip
  - Supports PEP 503 simple repository API

- **`upload_to_s3.sh`** - Uploads wheels and index to S3
  - Syncs wheels to `s3://bucket/packages/`
  - Syncs index to `s3://bucket/simple/`
  - Sets appropriate content types and cache headers

### Utility Scripts

- **`download_dependency_wheels.py`** - Downloads dependency wheels
- **`normalize_wheel_versions.py`** - Normalizes wheel versions
- **`organize_wheels.py`** - Organizes wheels for upload

## Usage

These scripts are used by the GitHub Actions workflow `.github/workflows/build-rocm-wheel.yml`.

### Example: Building Custom Wheels

```dockerfile
# In Dockerfile.rocm_base
COPY tools/vllm-rocm/pin_rocm_dependencies.py /tmp/
RUN python3 /tmp/pin_rocm_dependencies.py /install /app/vllm/requirements/rocm.txt
```

### Example: Cleaning Duplicates

```bash
chmod +x tools/vllm-rocm/cleanup_pypi_duplicates.sh
tools/vllm-rocm/cleanup_pypi_duplicates.sh artifacts/rocm-base-wheels all-wheels
```

### Example: Generating S3 Index

```bash
python3 tools/vllm-rocm/generate_s3_index.py \
  --wheels-dir all-wheels \
  --output-dir pypi-index \
  --s3-url "http://bucket.s3-website-region.amazonaws.com" \
  --rocm-version "7.1" \
  --python-version "3.12" \
  --gpu-arch "gfx942" \
  --vllm-version "v0.11.2"
```

## Adding New Custom Packages

See **[ADDING_PACKAGES.md](./ADDING_PACKAGES.md)** for a comprehensive guide on adding new custom packages.

**Quick summary:**
1. Add build stage to `docker/Dockerfile.rocm_base`
2. Update `pin_rocm_dependencies.py` package mapping
3. Update `cleanup_pypi_duplicates.sh` PACKAGES_TO_CHECK
4. Test the build

The rest of the pipeline automatically handles the new package!

## Architecture

The pipeline follows this flow:

1. **Build Stage** (`Dockerfile.rocm_base`): Builds custom ROCm wheels
2. **Pin Stage** (`Dockerfile.rocm`): Pins custom wheels in vLLM requirements
3. **Build vLLM**: Builds vLLM wheel with pinned dependencies
4. **Collect Dependencies**: Gathers all required wheels
5. **Cleanup**: Removes PyPI duplicates of custom packages
6. **Generate Index**: Creates PyPI-compatible index
7. **Upload**: Syncs to S3 for distribution

## See Also

- `.github/workflows/build-rocm-wheel.yml` - Main build workflow
- `docker/Dockerfile.rocm_base` - Custom wheel builds
- `docker/Dockerfile.rocm` - vLLM build with custom wheels
