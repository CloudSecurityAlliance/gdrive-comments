# CI and release lockfiles

Hash-pinned closures for **what this repository's automation installs**. Regenerate with
[`scripts/lock.sh`](../scripts/lock.sh); use `--upgrade` to re-resolve to the newest compatible
versions.

**Dependabot does not maintain these, and must not be pointed at them.** An earlier version of
this file said it did. The first run disproved it: Dependabot bumped `pydantic-core`
2.46.4 → 2.48.0 and left `pydantic==2.13.4`, which pins `pydantic-core==2.46.4`, and every CI job
failed with `ResolutionImpossible`. Dependabot edits individual pinned lines; **a fully-pinned
transitive lock has to be re-resolved as a graph**, not patched. `.github/workflows/relock.yml`
does that weekly and opens an issue when the pins have moved.

| File | Pins | Used by |
|---|---|---|
| `dev.txt` | the `.[dev]` closure | `lint`, the five-Python `test` matrix, and the release build's suite step |
| `build.txt` | `build` + `twine` | the release build's "Build sdist + wheel" step |
| `build-backend.txt` | `setuptools` | the same step, via `PIP_CONSTRAINT` — see below |
| `uv.txt` | `uv` itself | `relock.yml`, so the tool that regenerates the locks is not an unpinned download |

`*.in` are the inputs; `*.txt` are generated and should never be hand-edited.

## This does not pin what users get

`pyproject.toml` keeps lower-bound-only ranges, deliberately. Pinning a *library's*
dependencies pushes a resolution problem onto every application that installs it. Reproducible
CI and a permissive published package are different questions, and the 2026-07-22 audit was
right to call the permissive ranges "benign and standard for a library" (GA-#28) while the
2026-08-27 audit was right that CI needs the opposite (T18).

## `build-backend.txt` is the one that touches the artifact

`python -m build` creates **its own isolated venv** and installs `build-system.requires` into
it from PyPI. Pinning `build` and `twine` in the outer environment does not reach that env —
so the code that actually writes the wheel was the one thing still resolving freely, in the
job whose entire output is the published artifact.

`PIP_CONSTRAINT` reaches inside it. **Verified by falsification** rather than assumed: pointing
it at a file pinning `setuptools==82.0.0`, which contradicts our `build-system.requires =
["setuptools>=83"]`, makes the build fail with a resolver conflict. A constraint that was
silently ignored would have built happily.

## `--python-version 3.10` is load-bearing

`uv pip compile --universal` resolves against **the interpreter you are running**, not the
floor in `requires-python`, even when the input is that same `pyproject.toml`. Measured on a
3.12 machine: it pinned `rpds-py==2026.6.3`, which requires >=3.11 — a lockfile that installs
on four matrix legs and fails the fifth, at install time in CI rather than at compile time
here. With the floor given explicitly, uv emits marked entries
(`rpds-py==0.30.0 ; python_full_version < '3.11'`) and all five legs install.

## `PIP_CONSTRAINT` cannot be used for the editable installs

It is the obvious tool and it does not work. A constraints file **carrying hashes** puts pip
into hash-checking mode for the whole invocation, and an editable requirement then fails:

    ERROR: The editable requirement file:///... cannot be installed when requiring hashes,
    because there is no single file to hash.

So it appears on exactly one step — `python -m build`, which installs nothing editable. Every
other place that needs a pinned backend installs `build-backend.txt` and passes
`--no-build-isolation`, which reaches the same result without the global mode switch.

## What is deliberately NOT pinned

**The `security` job's dependency scan.** `pip-audit` exists to observe what a real install
resolves to; running it against a frozen set would have it audit *our lockfile* instead of
*what users get*, which is the one environment we do not need told about. It keeps resolving
freely, and that is the point rather than an oversight.

**The `security` job's editable build.** `pip install -e . pip-audit bandit` builds with
isolation and resolves freely, for the same reason as the line above: that job is meant to
look like a real user's install.

**`pip` itself.** The workflows no longer run `pip install --upgrade pip`, so pip is the one
the runner image ships. Upgrading it was an unpinned fetch from PyPI by the very tool that
then verified every other hash — bootstrapping a hash check with an unverified download.
Using the runner's pip removes the fetch instead of pinning it.

## When the lock drifts from `pyproject.toml`

`tests/test_lockfiles.py` fails on the PR that introduces the drift, in the `lint` job. Without
it, a dependency added to `pyproject.toml` and not locked here surfaces as an `ImportError` in
the middle of the test matrix — a true failure with a misleading cause.
