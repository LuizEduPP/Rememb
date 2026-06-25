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

- `release.published`: builds, tests, and publishes to PyPI
- `workflow_dispatch`: builds and tests only (publish job is skipped)

Each run does the following before publishing:

1. checks out the repository
2. installs the project with development dependencies
3. runs the test suite
4. runs `python -m py_compile src/rememb/*.py`
5. builds both wheel and sdist with `python -m build`
6. uploads the built `dist/` artifacts into the workflow
7. downloads the artifacts in the publish job and publishes them with `pypa/gh-action-pypi-publish` (release event only)

When publishing through `pypa/gh-action-pypi-publish@release/v1`, PyPI attestations are generated and uploaded automatically by default.

The publish job runs only when `github.event_name == 'release'`. Manual `workflow_dispatch` runs validate the build pipeline but do **not** upload to PyPI.

## Required PyPI Configuration

Configure Trusted Publishers for this repository before expecting the workflow to succeed.

### PyPI

Create a Trusted Publisher on PyPI with these values:

- project name: `rememb`
- repository owner: `LuizEduPP`
- repository name: `Rememb`
- workflow file: `.github/workflows/release.yml`
- environment: `pypi`

Important:

- The PyPI project name is lowercase: `rememb`.
- The GitHub repository name must match the repository claims exactly: `Rememb`.
- The tag must point to a commit whose `pyproject.toml` version matches the release tag (e.g. tag `v0.4.13` → `version = "0.4.13"`).

Strongly recommended:

- require manual approval for the GitHub environment `pypi`

## Required GitHub Configuration

Create this GitHub environment in the repository settings:

- `pypi`

Recommended protection:

- require reviewers for `pypi`

No `PYPI_API_TOKEN` secrets are required for this flow.

If old token-based publishing was configured previously, revoke those tokens and remove the old secrets.

## How to Publish

Create or publish a GitHub Release. The `release.published` event triggers the PyPI publish job.

Before tagging, bump `version` in `pyproject.toml` and commit on the branch you will tag.

## Failure Model

If Trusted Publishing is not configured yet, the publish job will fail even if build and tests pass.

If the tag points to a commit with the wrong package version, PyPI rejects the upload with a file-already-exists or version mismatch error.

That failure is expected and means the repository-side pipeline is ready, but the PyPI-side trust relationship or release tag has not been completed correctly yet.
