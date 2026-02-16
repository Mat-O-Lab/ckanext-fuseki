# Dynamic Versioning with setuptools-scm

This project now uses **setuptools-scm** for automatic version management based on git tags.

## How It Works

- Version numbers are **automatically derived from git tags**
- No need to manually update version numbers in code
- Development versions are automatically numbered between releases

## Creating a Release

To create a new release version, simply create and push a git tag:

```bash
# Create a new version tag (e.g., v1.0.0, v1.1.0, v2.0.0)
git tag v1.0.0

# Push the tag to remote
git push origin v1.0.0
```

## Version Formats

- **Tagged release**: `1.0.0` (from tag `v1.0.0`)
- **Development version**: `1.0.0.dev5+g1234abc` (5 commits after tag v1.0.0)
- **No tags yet**: `0.0.1.dev0` (fallback version)

## Installation

The package can still be installed the same way:

```bash
# For development (editable install)
pip install -e .

# For production
pip install .
```

## Requirements

The build system requires:
- `setuptools>=61.0`
- `wheel`
- `setuptools-scm>=8.0`

These are automatically installed during the build process.

## Migration from Old Setup

The previous `setup.py` with hardcoded version has been replaced with:
- ✅ **pyproject.toml**: Modern configuration following PEP 517/518
- ✅ **Minimal setup.py**: Kept for backward compatibility
- ✅ **Dynamic versioning**: Automatic from git tags
- ✅ **Fixed MANIFEST.in**: Corrected paths for package data

All functionality remains the same, but version management is now automated.
