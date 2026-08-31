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

**This is now checked, not just written down.** `scripts/check_controls.py` asserts all three
externally-configured controls — the constrained publisher, this environment's required
reviewers, and branch protection on `main`:

```bash
GITHUB_TOKEN=$(gh auth token) python scripts/check_controls.py
```

It runs weekly (`.github/workflows/controls.yml`) and in the release build, so a removed
reviewer stops the release that would otherwise publish unattended. Two of the three need no
credential at all; branch protection needs admin rights, so in CI it reports `????` unless an
read-only `CONTROLS_TOKEN` secret is configured — **it is, since 2026-08-31, expiring
2027-09-01** (see the rotation notice at the top of `TODO.md`). Run it locally before a release and
you get all three.

The check reports **OK / VIOLATED / UNVERIFIABLE** and never collapses the third into the
first: a control check that cannot reach its evidence and exits 0 reads as a control while
asserting nothing. It detects **drift**, not an attacker with repo access — who could edit the
check. That is the same self-referential limit as above, with the same answer: what survives is
what PyPI and GitHub enforce.

## Version numbers: an audit opens `x.y.0`, its fixes continue in `x.y.*`

**Decided 2026-08-27.** Two rules, and the first is the useful one.

**A security audit opens a new minor.** The first release carrying remediation from an audit is
`x.y.0`. Subsequent batches of fixes **from the same audit** are patches — `x.y.1`, `x.y.2` — so
the version says how far through remediation a release is, not just that something changed:

| | |
|---|---|
| `0.30.0` | audit `2026-08-27-01` — remediation opens (#181, the exploitable flaw) |
| `0.30.1` | same audit, next batch |
| `0.30.2` | same audit, next batch |
| `0.31.0` | the **next** audit's remediation opens |

Somebody reading `0.30.4` can tell it is the fifth release against the first audit. That is
information a bare minor bump per change throws away, and remediation is exactly the case where
"which batch of what" is the question people ask.

**Otherwise:** a **patch** is fixes only — nothing a caller could notice except the bug going
away. A **minor** is anything else: a new tool or parameter, a **changed default**, removed
behaviour, or anything a configuration could depend on. `0.30.0` is correctly a minor on this
rule as well as the audit rule, because it changed an observable default (`USER_ENTERED` →
`RAW`).

Note this is a *communication* convention, not a compatibility promise:
[`API-STABILITY.md`](API-STABILITY.md) says pre-1.0.0 nothing is frozen and that remains true.
It is still worth having, because "is this safe to take?" is the question a release list should
answer at a glance.

## Publishing is not optional

**A version bump means carry it to PyPI.** Do not stop at a staged release: the fix only reaches
installs on publish, and the README shown on PyPI is frozen per release, so documentation
corrections wait for the next version regardless of what `main` says.

**The workflow is two jobs, and the approval now sits between them.** `build` runs the security
gate, the suite, the build and the sdist guard, holding **no** publishing credential; `publish`
holds `id-token: write` and does nothing but download the artifacts and hand them to the PyPA
action — it does not even check out the repository.

So the run reports `waiting` **after** `build` has passed rather than before it starts, which is
the better moment: you are approving a build you can see succeeded. Approving it is part of
cutting the release:

```bash
RUN=$(gh run list --workflow=release.yml --limit 1 --json databaseId -q '.[0].databaseId')
gh api --method POST "repos/$REPO/actions/runs/$RUN/pending_deployments" --input - <<'JSON'
{"environment_ids":[18642982745],"state":"approved","comment":"why this is safe to ship"}
JSON
```

`gh api -f 'environment_ids[]=…'` fails under zsh — the brackets glob. Use `--input -`.

Then verify **before** reporting it done: the per-version PyPI endpoint, the simple index, and a
clean-venv install.

**Checking PEP 740 attestations: use the integrity endpoint, not the project JSON.**

```bash
curl -s -H 'Accept: application/vnd.pypi.integrity.v1+json' \
  "https://pypi.org/integrity/csa-google-workspace/$V/csa_google_workspace-$V-py3-none-any.whl/provenance" \
  | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["attestation_bundles"]), "bundle(s)")'
```

The `/pypi/<name>/<version>/json` response has **no `provenance` key at all** — for any release,
attested or not. Reading its absence as "attestations are missing" wrongly suggested the
build/publish split had broken them; the integrity endpoint showed one bundle for both the new
release and the one before it.

**Do not add steps to the `publish` job.** Anything that runs there — a checkout, a `pip install`,
a version check — executes beside a live publishing credential, which is precisely what the split
removed. `tests/test_release_workflow_shape.py` asserts the shape, including an allowlist of the
actions that job may use, so a new one has to be added there deliberately.

**The two indexes lag independently, in either direction.** After v0.29.0 the project-level JSON
endpoint was behind and the simple index current; after v0.30.0 it was the reverse.
`check_release_history.py` treats a claimed version confirmed by **either** as published, which
is why it no longer fails on a true claim.

**The consequential direction is a stale simple index, because that is what pip resolves from.**
After v0.30.0 a clean-venv install returned **0.29.0** — the version the release had just fixed.

**Two different causes produce an identical symptom, and only one of them is PyPI's.** Both look
like `No matching distribution found`, with a version list that stops at the previous release:

* **PyPI's CDN edge is stale.** `--no-cache-dir` cannot help — it bypasses *pip's* cache, not
  PyPI's. This is the case the retry loop below exists for.
* **pip's own HTTP cache of the index page is warm.** A fresh `venv` does *not* clear this: the
  cache lives in `~/Library/Caches/pip`, outside any virtualenv, so "clean venv" is not clean in
  the way that matters here. `--no-cache-dir` fixes it immediately.

Seen at v0.32.0, where the simple index, both JSON endpoints and the integrity endpoint all
confirmed the release while `pip install` insisted the newest version was 0.31.1 — a false alarm
that reads exactly like a failed publish. **So pass `--no-cache-dir` on the verification install
always**: it costs nothing, and it removes one of the two explanations for free.

**And polling an endpoint first is NOT sufficient** — tried at v0.30.1 and it still failed. The
simple index reported `0.30.1` present, and pip then installed `0.30.0` from a different CDN edge.
Requesting an index yourself tells you about the edge *you* reached, not the one pip will.

So the only reliable verification is to **install and assert the version, retrying until it
matches**:

```bash
for i in $(seq 1 12); do
  rm -rf /tmp/vcheck && python3 -m venv /tmp/vcheck
  /tmp/vcheck/bin/pip install -q --no-cache-dir 'csa-google-workspace[mcp]'
  V=$(/tmp/vcheck/bin/python -c 'import csa_google_workspace as m; print(m.__version__)')
  [ "$V" = "$EXPECTED" ] && break
  sleep 20
done
```

Do it this way round and a stale edge costs a retry. Do it the other way and the verification
step tests the **old artifact** and *passes* — which is worse than not checking at all, because
it is a green light on exactly the thing you were replacing. That happened twice before the rule
was written this way.

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
   pip install --no-cache-dir csa-google-workspace
   python -c "import csa_google_workspace; print(csa_google_workspace.__version__)"
   ```
   `--no-cache-dir` is not optional here — see the two-causes note above. Without it, a warm pip
   index cache reports the *previous* version and looks exactly like a failed publish.

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
