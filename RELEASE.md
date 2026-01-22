# Release Guide

This guide explains how to release a new version of `django-brevo-analytics`.

## Prerequisites

1. **PyPI Account**: Create account at https://pypi.org
2. **API Token**: Generate API token at https://pypi.org/manage/account/token/
3. **GitHub Repository**: Push code to https://github.com/guglielmo/django-brevo-analytics
4. **Install build tools**:
   ```bash
   pip install build twine
   ```

## Release Process

### 1. Update Version

Update version in `brevo_analytics/__init__.py`:

```python
__version__ = '0.2.0'  # Change to new version
```

### 2. Update CHANGELOG.md

Add release notes to `CHANGELOG.md`:

```markdown
## [0.2.0] - 2026-01-22

### Added
- Feature description

### Changed
- Change description

### Fixed
- Fix description
```

### 3. Commit Changes

```bash
git add brevo_analytics/__init__.py CHANGELOG.md
git commit -m "Release v0.2.0"
git push origin main
```

### 4. Manual Release to PyPI

#### Build the package

```bash
# Clean previous builds
rm -rf dist/ build/ *.egg-info

# Build source distribution and wheel
python -m build

# Check the build
twine check dist/*
```

#### Upload to PyPI

```bash
# Upload to PyPI (will prompt for API token)
twine upload dist/*

# Or use environment variable
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-your-api-token-here
twine upload dist/*
```

### 5. Automated Release via GitHub (Recommended)

#### Setup (one-time)

1. Go to https://github.com/guglielmo/django-brevo-analytics/settings/secrets/actions
2. Add new repository secret:
   - Name: `PYPI_API_TOKEN`
   - Value: Your PyPI API token (starts with `pypi-`)

#### Create Release

1. **Tag the release**:
   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```

2. **Create GitHub Release**:
   - Go to https://github.com/guglielmo/django-brevo-analytics/releases/new
   - Choose tag: `v0.2.0`
   - Release title: `v0.2.0`
   - Description: Copy from CHANGELOG.md
   - Click "Publish release"

3. **Automated deployment**:
   - GitHub Actions will automatically build and publish to PyPI
   - Monitor at https://github.com/guglielmo/django-brevo-analytics/actions

## Version Numbering

Follow [Semantic Versioning](https://semver.org/):

- **MAJOR** (1.0.0): Incompatible API changes
- **MINOR** (0.2.0): New functionality, backwards-compatible
- **PATCH** (0.1.1): Bug fixes, backwards-compatible

## Testing the Release

After publishing to PyPI:

```bash
# Create test environment
python -m venv test_env
source test_env/bin/activate

# Install from PyPI
pip install django-brevo-analytics==0.2.0

# Verify installation
python -c "import brevo_analytics; print(brevo_analytics.__version__)"
```

## Troubleshooting

### Build fails with missing files

Update `MANIFEST.in` to include missing files:
```
recursive-include brevo_analytics/new_directory *
```

### Upload fails with authentication error

Check PyPI token:
- Token must start with `pypi-`
- Use `__token__` as username
- Token must have upload permissions

### GitHub Actions fails

1. Check Actions log: https://github.com/guglielmo/django-brevo-analytics/actions
2. Verify `PYPI_API_TOKEN` secret is set
3. Ensure tag matches release version

## First-Time PyPI Setup

If this is the first release:

```bash
# Register the project on PyPI (first time only)
twine upload dist/*

# This will create the project page at:
# https://pypi.org/project/django-brevo-analytics/
```

## Resources

- PyPI Package: https://pypi.org/project/django-brevo-analytics/
- GitHub Repository: https://github.com/guglielmo/django-brevo-analytics
- Documentation: https://github.com/guglielmo/django-brevo-analytics/blob/main/README.md
