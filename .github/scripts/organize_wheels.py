#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
"""
Script to organize wheels by size for GitHub Pages (<100MB) and GitHub Releases (>100MB).
"""

import os
import sys
import shutil
from pathlib import Path
from datetime import datetime

SIZE_LIMIT = 100 * 1024 * 1024  # 100MB

# Validate environment
print("Validating environment...")
if 'GITHUB_OUTPUT' not in os.environ:
    print("ERROR: GITHUB_OUTPUT environment variable not set!", file=sys.stderr)
    print("This script must be run in a GitHub Actions environment.", file=sys.stderr)
    sys.exit(1)
print(f"GITHUB_OUTPUT is set to: {os.environ['GITHUB_OUTPUT']}")

# Validate artifacts directory exists
artifacts_dir = Path("artifacts")
print(f"\nChecking for artifacts directory at: {artifacts_dir.absolute()}")

if not artifacts_dir.exists():
    print(f"ERROR: Artifacts directory not found at: {artifacts_dir.absolute()}", file=sys.stderr)
    print(f"\nCurrent working directory: {Path.cwd()}", file=sys.stderr)
    print(f"\nContents of current directory:", file=sys.stderr)
    for item in sorted(Path.cwd().iterdir()):
        print(f"  - {item.name}", file=sys.stderr)
    sys.exit(1)

if not artifacts_dir.is_dir():
    print(f"ERROR: {artifacts_dir} exists but is not a directory!", file=sys.stderr)
    sys.exit(1)

print(f"Artifacts directory found: {artifacts_dir.absolute()}")

# Create directories
packages_dir = Path("pypi-repo/packages")
large_dir = Path("pypi-repo/packages-large")
small_dir = Path("pypi-repo/packages-small")

print("\nCreating output directories...")
packages_dir.mkdir(parents=True, exist_ok=True)
large_dir.mkdir(parents=True, exist_ok=True)
small_dir.mkdir(parents=True, exist_ok=True)
print(f"  - {packages_dir}")
print(f"  - {large_dir}")
print(f"  - {small_dir}")

# Find all wheels
print("\nCollecting wheels from artifacts...")
print(f"Searching in: {artifacts_dir.absolute()}")
all_wheels = list(artifacts_dir.rglob("*.whl"))
total = len(all_wheels)

if total == 0:
    print(f"\nWARNING: No wheels found in {artifacts_dir}/", file=sys.stderr)
    print(f"\nArtifacts directory structure:", file=sys.stderr)
    items_found = False
    for item in artifacts_dir.rglob("*"):
        if item.is_file():
            items_found = True
            print(f"  {item.relative_to(artifacts_dir)}", file=sys.stderr)
    if not items_found:
        print("  (directory is empty)", file=sys.stderr)
    print(f"\nERROR: Cannot proceed without any wheels!", file=sys.stderr)
    sys.exit(1)

print(f"Found {total} wheels to process\n")

# Copy and separate in one pass
large_count = 0
small_count = 0
large_total_size = 0
small_total_size = 0

for i, wheel in enumerate(all_wheels, 1):
    try:
        size = wheel.stat().st_size

        # Determine target directory
        if size > SIZE_LIMIT:
            target_dir = large_dir
            large_count += 1
            large_total_size += size
        else:
            target_dir = small_dir
            small_count += 1
            small_total_size += size

        # Copy to target
        shutil.copy2(wheel, target_dir / wheel.name)

        # Progress indicator
        if i % 50 == 0 or i == total:
            pct = i * 100 // total
            print(f"Progress: {i}/{total} wheels ({pct}%)")

    except Exception as e:
        print(f"WARNING: Failed to process {wheel.name}: {e}", file=sys.stderr)

# Copy small wheels to packages/ for GitHub Pages
print(f"\nCopying {small_count} small wheels to packages directory...")
for wheel in small_dir.glob("*.whl"):
    shutil.copy2(wheel, packages_dir / wheel.name)

# Summary
print(f"\n{'='*70}")
print(f"Wheel Organization Complete!")
print(f"{'='*70}")
print(f"Total wheels: {total}")
print(f"  Large wheels (>100MB): {large_count} -> GitHub Releases ({large_total_size/(1024**3):.2f} GB)")
print(f"  Small wheels (<100MB): {small_count} -> GitHub Pages ({small_total_size/(1024**2):.1f} MB)")
print(f"{'='*70}\n")

# List examples
large_wheels = sorted(large_dir.glob("*.whl"), key=lambda x: x.stat().st_size, reverse=True)
if large_wheels:
    print(f"Large wheels (showing {min(5, len(large_wheels))} of {len(large_wheels)}):")
    for w in large_wheels[:5]:
        size_mb = w.stat().st_size / (1024*1024)
        print(f"  - {w.name} ({size_mb:.1f} MB)")

small_sample = list(small_dir.glob("*.whl"))[:5]
if small_sample:
    print(f"\nSmall wheels (showing 5 of {small_count}):")
    for w in small_sample:
        size_mb = w.stat().st_size / (1024*1024)
        print(f"  - {w.name} ({size_mb:.1f} MB)")

# Set output for next steps
release_tag = f"wheels-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

print(f"\nSetting GitHub Actions output...")
try:
    with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
        f.write(f"release_tag={release_tag}\n")
    print(f"Release tag set: {release_tag}")
    print(f"Successfully wrote to GITHUB_OUTPUT")
except Exception as e:
    print(f"\nERROR: Failed to write to GITHUB_OUTPUT: {e}", file=sys.stderr)
    sys.exit(1)

print("\nScript completed successfully!")
