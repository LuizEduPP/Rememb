# Release Process

This repository publishes releases through GitHub Actions with PyPI Trusted Publishing.

## Goals

- avoid long-lived PyPI API tokens
- build reproducible wheel and sdist artifacts in CI
- publish with GitHub OIDC
- attach PyPI-compatible attestations automatically during upload

## Workflow Files

- CI validation: [.github/workflows/ci.yml](.github/workflows/ci.yml)
- Release publishing: [.github/workflows/release.yml](.github/workflows/release.yml)

## What the Release Workflow Does

The release workflow has two entry points:

- `release.published`: builds, tests and publishes to PyPI
- `workflow_dispatch`: builds, tests and publishes to TestPyPI

Each run does the following before publishing:

1. checks out the repository
2. installs the project with development dependencies
3. runs the test suite
4. runs `python -m py_compile src/rememb/*.py`
5. builds both wheel and sdist with `python -m build`
6. uploads the built `dist/` artifacts into the workflow
7. downloads the artifacts in the publish job and publishes them with `pypa/gh-action-pypi-publish`

When publishing through `pypa/gh-action-pypi-publish@release/v1`, PyPI attestations are generated and uploaded automatically by default.

## Required PyPI Configuration

Configure Trusted Publishers for this repository before expecting the workflow to succeed.

### PyPI

Create a Trusted Publisher on PyPI with these values:

- project name: `rememb`
- repository owner: `LuizEduPP`
- repository name: `rememb`
- workflow file: `.github/workflows/release.yml`
- environment: `pypi`

Strongly recommended:

- require manual approval for the GitHub environment `pypi`

### TestPyPI

Create a second Trusted Publisher on TestPyPI with these values:

- project name: `rememb`
- repository owner: `LuizEduPP`
- repository name: `rememb`
- workflow file: `.github/workflows/release.yml`
- environment: `testpypi`

## Required GitHub Configuration

Create these GitHub environments in the repository settings:

- `pypi`
- `testpypi`

Recommended protection:

- require reviewers for `pypi`
- keep `testpypi` without manual approval for faster pipeline checks

No `PYPI_API_TOKEN` or `TEST_PYPI_API_TOKEN` secrets are required for this flow.

If old token-based publishing was configured previously, revoke those tokens and remove the old secrets.

## How to Publish

### TestPyPI

Use GitHub Actions and manually run the `Release` workflow. That path publishes to TestPyPI.

### PyPI

Create or publish a GitHub Release. The `release.published` event will trigger the PyPI publish job.

## Failure Model

If Trusted Publishing is not configured yet, the publish job will fail even if build and tests pass.

That failure is expected and means the repository-side pipeline is ready, but the PyPI-side trust relationship has not been completed yet.