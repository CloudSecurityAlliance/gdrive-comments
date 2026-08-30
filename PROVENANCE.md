# Provenance

Who built this, how, and how you can check what you installed came from what you can read.

This exists because the project is a security library that holds a full-Drive OAuth token, and
"who wrote this and who reviewed it" is part of its supply chain rather than trivia. It is also
here because the honest answer is more unusual than the usual one, and inferring it from prose
style is worse than reading it.

## Authorship

**Every non-bot commit is authored `Kurt Seifried <kurt@seifried.org>`** — 208 of them at the
time of writing, plus 2 from Dependabot. He owns the repository, the Google Cloud project, the
PyPI trusted-publisher configuration, and every design decision recorded in
`docs/superpowers/specs/`.

**The content — code, tests, specs, plans, this file — was written by an AI assistant (Claude,
via Claude Code) working from his direction.** Not "a large share", which is how this paragraph
read until 2026-08-30 and understated it: the drafting is the assistant's, in sessions where he
sets the goals, chooses between options, rejects approaches, corrects framings, and reviews what
lands. The commits are attributed to him because **he is accountable for them**, which is the
part attribution is actually for.

That is stated plainly rather than softened because a provenance document that hedges its own
central fact is worth less than no document. It is also why there are **no per-commit
"AI-assisted" trailers** and will not be: a trailer exists to *distinguish*, and here there is
nothing to distinguish. A marker on every commit is noise. (A handful of early commits carry
`Co-authored-by:` trailers from tooling defaults; they mark nothing this paragraph does not
already say about all of them.)

Two things follow, and both matter more than the attribution itself:

- **Review is single-person.** There is one human in the loop, and required approving reviews on
  `main` are set to 0 so the solo flow merges on green checks. What stands between a mistake and
  `main` is the CI suite (unit tests, ruff, mypy, bandit, pip-audit, CodeQL, a coverage floor),
  the live-verification habit for anything touching Google, and one person reading the diff.
  That is more than many small projects have and less than a second reviewer; calling it what it
  is seems better than implying a review board.
- **Reasoning is unusually well recorded, and that is deliberate.** Commit messages here argue
  rather than summarise, `experiments/*/RESULTS.md` carry dated empirical probes, and
  `docs/superpowers/specs|plans/` hold the design arguments. When Google's documentation and a
  probe disagree, the probe wins and the finding is folded back into `research/`. If you want to
  know *why* something is the way it is, the history will usually tell you — see
  [`docs/DECISIONS.md`](docs/DECISIONS.md) for an index.

If that division of labour disqualifies this library for your purposes, that is a legitimate
call and this document exists so you can make it early.

## Verifying a release

Every release is built and published by GitHub Actions from a tag, over
[PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OIDC — no API token
exists to leak), with [PEP 740](https://peps.python.org/pep-0740/) attestations attached. Nobody
uploads by hand; `twine upload` is not part of the process.

You can check the attestation yourself without asking us:

```bash
# What PyPI holds for a given file
curl -s https://pypi.org/integrity/csa-google-workspace/0.11.0/\
csa_google_workspace-0.11.0-py3-none-any.whl/provenance | jq '
  .attestation_bundles[0].publisher'
# -> {"kind": "GitHub", "repository": "CloudSecurityAlliance/csa-google-workspace", ...}
```

Or with `pypi-attestations`:

```bash
pipx run pypi-attestations verify pypi \
  --repository https://github.com/CloudSecurityAlliance/csa-google-workspace \
  csa_google_workspace-0.11.0-py3-none-any.whl
```

What that establishes: the artifact was built by GitHub Actions in this repository, from the
workflow at that tag. What it does **not** establish: that the tag's contents are what you
expect. For that, read the tag.

## Release history

The changelog records **every change**, including versions that were never published — those
were bumped in code as work landed and shipped together in a later release. Headings say which.

Three records have to agree, and they are checked rather than trusted:

| Record | What it means | Checked by |
|---|---|---|
| `CHANGELOG.md` | what changed, and why | `tests/test_release_history.py` (offline, in CI) |
| git tags | what was released | `scripts/check_release_history.py` |
| PyPI | what you can install | same script |

Run `python scripts/check_release_history.py` before cutting a release. It found a real
discrepancy the first time it ran, which is the argument for having it.

## Yanking

A published version is permanent — it can be **yanked** (hidden from resolvers that have
alternatives, still installable when pinned) but never deleted or re-uploaded. So the bar for
yanking is *"installing this by accident is harmful"*, not *"this is old"*.

We would yank for:

- a credential leaked in the artifact, or a dependency with a known exploited vulnerability that
  the version cannot avoid;
- a bug that **loses or corrupts a user's document data**, or one that causes a write where the
  configured policy should have refused it — the policy failing *open* is in this category;
- **untrusted document content reaching somewhere it executes.** Prompt injection through
  document and comment text is the primary risk in [`SECURITY.md`](SECURITY.md), and this is the
  category for when that text stops being *reported* and starts being *run* — added 2026-08-26
  after `v0.24.0` shipped a comment export that wrote `=cmd|' /C calc'!A0` into a CSV
  unescaped, where Excel would execute it on open. The three categories above were written from
  the failures we had already had; this one was in the threat model all along and not in the
  list;
- an artifact whose contents do not match its tag.

We would **not** yank for: an outdated tool surface, a superseded API, a bug with an obvious
workaround, or embarrassment. Superseding is the normal remedy; yanking is for when *not*
upgrading is dangerous.

A yank is announced in `CHANGELOG.md` and in the GitHub release for the affected version, with
the reason and the version to move to.

## Secret hygiene in history

`CLAUDE.md` forbids committing OAuth secrets, probe transcripts, or extracted document data. As
of 2026-08-25, across 177 commits:

- **trufflehog** — 0 verified, 0 unverified secrets.
- **gitleaks** — no findings. One earlier hit was triaged as a false positive (the
  `generic-api-key` rule firing on the entropy of a sentence containing
  `CSA_GW_INTEGRATION=1`, a documented environment variable whose value is `1`) and is
  allowlisted in `.gitleaks.toml` with that reasoning, so a real finding is not lost in noise.
- `git log --all --name-only` shows no `client_secret*`, `credentials.json`, `token*.json`,
  `.pem` or transcript path ever committed.

Re-run both before any release that changes what is packaged:

```bash
gitleaks git --no-banner --redact -v .
trufflehog git file://. --results=verified,unknown
```

## Reporting a problem

Security issues go through
[GitHub security advisories](https://github.com/CloudSecurityAlliance/csa-google-workspace/security/advisories/new),
privately — see [`SECURITY.md`](SECURITY.md), which also carries the threat model.
