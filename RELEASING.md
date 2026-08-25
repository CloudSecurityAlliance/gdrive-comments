# Releasing to PyPI

Publishing is automated: **publishing a GitHub Release** triggers
[`.github/workflows/release.yml`](.github/workflows/release.yml), which runs the tests,
builds the sdist + wheel, and uploads to PyPI via **Trusted Publishing (OIDC)** — no API
token is stored anywhere.

## One-time setup (maintainer, on PyPI)

Do this once, before the first release. PyPI supports a "pending publisher", so the project
need not exist yet.

1. Sign in to <https://pypi.org> with the account that will own the project (the CSA org
   account, or a maintainer's).
2. Go to **Your projects → Publishing** (or, for a brand-new project,
   <https://pypi.org/manage/account/publishing/>) and **Add a pending publisher** with:
   - **PyPI project name:** `csa-google-workspace`
   - **Owner:** `CloudSecurityAlliance`
   - **Repository name:** `csa-google-workspace`
   - **Workflow name:** `release.yml`
   - **Environment name:** **`pypi`** — *not blank, and not the `release` placeholder the form
     shows in grey.* It must match `environment:` on the `publish` job in
     `.github/workflows/release.yml`.
3. Create the matching GitHub Environment: repo **Settings → Environments → `pypi`**, with
   **required reviewers** set to the repo owner. This is what makes each publish stop for a
   human.
4. That's it — no token, no GitHub secret. GitHub Actions authenticates to PyPI over OIDC.

**Why the environment name is not optional.** An unconstrained publisher (`Environment name:
(Any)`, which is what PyPI defaults to) accepts a publish from *any* environment — so the
approval gate would be enforced only by a line of YAML **inside the repo being published**.
Anyone able to edit the workflow could delete `environment: pypi` and PyPI would still accept
the upload; the control guarding releases would be guarded by the thing it protects. With the
publisher constrained, removing that line *breaks* publishing rather than bypassing review.

If you ever see PyPI email *"Trusted Publisher … can be made more secure"*, the binding has come
unconstrained — fix it by adding the constrained publisher first, confirming it appears, then
removing the unconstrained one, so the project is never left without a working publisher.

## Cut a release

1. Make sure `main` is green and pick the version. Bump it in **one place** —
   `src/csa_google_workspace/__init__.py` `__version__` (pyproject reads it dynamically) —
   and add a dated entry to `CHANGELOG.md`. Merge that via the normal PR flow.
2. Tag and publish a GitHub Release on the merge commit:
   ```bash
   gh release create v0.1.0 --title v0.1.0 --notes-file <(sed -n '/## 2026-.*v0.1.0/,/^## /p' CHANGELOG.md)
   # or: gh release create v0.1.0 --generate-notes
   ```
   The tag **must** match the version (`v0.1.0` ↔ `__version__ = "0.1.0"`).
3. Publishing the release starts the `release` workflow. Watch it:
   ```bash
   gh run watch
   ```
4. Verify the upload — <https://pypi.org/project/csa-google-workspace/> — then in a clean venv:
   ```bash
   pip install csa-google-workspace
   python -c "import csa_google_workspace; print(csa_google_workspace.__version__)"
   ```

## Notes

- A PyPI version number is **permanent** — it can be yanked but never re-uploaded. Get the
  version right before publishing.
- `requires-python` is `>=3.10`; the wheel is pure-Python (`py3-none-any`).
- The package ships `py.typed`, so downstream `mypy`/`pyright` consume its type hints.

## Before you tag

```bash
python scripts/check_release_history.py     # CHANGELOG vs git tags vs PyPI
gitleaks git --no-banner --redact -v .      # full history
trufflehog git file://. --results=verified,unknown
```

The first of those exists because the changelog once claimed eleven versions nobody could
install: bumping `__version__` is free, publishing is a separate gated act, and the two drift.
`tests/test_release_history.py` catches part of it offline in CI; the script does the three-way
reconcile that needs network and tags.

Note the ordering constraint: **the README is frozen on PyPI at publish time.** A documentation
fix reaches PyPI only on the next version bump, so land README changes *before* cutting the tag,
not after.

## Yanking

The policy — when we would yank rather than supersede, and what gets announced where — is in
[`PROVENANCE.md`](./PROVENANCE.md#yanking). Short version: the bar is "installing this by
accident is harmful", not "this is old".
