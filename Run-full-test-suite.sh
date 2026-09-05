#!/bin/zsh
#
# Run-full-test-suite.sh
#
# The conformance rig: run everything GitHub Actions cannot.
# Spec: docs/superpowers/specs/2026-09-05-conformance-rig.md
#
# By DEFAULT this tests the LATEST RELEASE FROM PyPI, not this checkout — because a
# packaging error, a missing file, or a dependency resolving differently on a clean
# machine is invisible to a source test. `--version tree` is available and is always
# an explicit choice, never a fallback.
#
# Usage:
#   ./Run-full-test-suite.sh                     # latest PyPI release, all unattended layers
#   ./Run-full-test-suite.sh --check             # prerequisites only, run nothing
#   ./Run-full-test-suite.sh --setup             # install/upgrade + register with Claude Code
#   ./Run-full-test-suite.sh --version 0.50.0    # a specific release, for bisecting
#   ./Run-full-test-suite.sh --version tree      # this working checkout
#   ./Run-full-test-suite.sh --layers 2,2ro      # just these layers
#   ./Run-full-test-suite.sh --folder <id|url>   # create test files in THIS Drive folder
#                                                # (default: a dated folder, trashed after)
#   ./Run-full-test-suite.sh --ai                # machine-readable timestamped output
#   ./Run-full-test-suite.sh --claude            # hand the results to Claude Code to triage
#

set -e

# --- Configuration ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PKG="csa-google-workspace"
CONFIG_DIR="$HOME/.csa_google_workspace"
CLIENT_SECRETS="${CSA_GW_CLIENT_SECRETS:-$CONFIG_DIR/client_secret.json}"
TOKEN_RW="${CSA_GW_TOKEN:-$CONFIG_DIR/token.json}"
TOKEN_RO="$CONFIG_DIR/token.readonly.json"
RIG_DIR="$HOME/.csa_gw_rig"           # venv + logs live OUTSIDE the checkout, on purpose
RIG_VENV="$RIG_DIR/venv"
RUN_LOG="$RIG_DIR/last-run.log"

# --- Which machine is this? -------------------------------------------------
# The rig is specified as a Mac (spec §6) — the editor-automation recipe is ⌘-based and
# Google Docs' key handling differs by platform. But somebody will try it elsewhere, and
# "command not found" is a worse answer than "here is the setup script for your OS".
case "$(uname -s 2>/dev/null)" in
    Darwin)                 OS_KIND=macos ;;
    Linux)                  OS_KIND=linux ;;
    MINGW*|MSYS*|CYGWIN*)   OS_KIND=windows ;;
    *)                      OS_KIND=unknown ;;
esac

DESKTOP_SETUP_REPO="https://github.com/CloudSecurityAlliance/DesktopSetup"

# Everything this rig needs — Claude Code, gh, Python, and the csa-google-workspace
# plugin itself — is installed by DesktopSetup. Telling somebody to install six things
# one at a time when one script does the lot is how a setup gets abandoned halfway.
desktop_setup_hint() {
    case "$OS_KIND" in
        macos)
            info "Run CSA DesktopSetup first — it installs all of the above:"
            info "  bash -c \"\$(curl -fsSL -H 'Cache-Control: no-cache' \\"
            info "    https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-ai-tools.sh)\""
            ;;
        windows)
            info "Run CSA DesktopSetup first. Windows needs a ONE-TIME PowerShell step."
            info ""
            info "  If this is a work laptop managed by IT, ask them before changing the"
            info "  execution policy — it is a security setting."
            info ""
            info "  1. PowerShell AS ADMINISTRATOR:  Get-ExecutionPolicy     <- note the value"
            info "  2. PowerShell AS ADMINISTRATOR:  Set-ExecutionPolicy RemoteSigned   (Y)"
            info "  3. A NORMAL PowerShell window:"
            info "       irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-ai-tools.ps1 -Headers @{'Cache-Control'='no-cache'} | iex"
            info "  4. PowerShell AS ADMINISTRATOR:  Set-ExecutionPolicy <value from step 1>"
            info ""
            info "  The no-cache header forces a fresh download — without it a stale copy"
            info "  from the CDN edge can persist for a few minutes after a fix ships."
            ;;
        *)
            info "Setup scripts: $DESKTOP_SETUP_REPO"
            info "There is no published script for this OS; install the tools above by hand."
            ;;
    esac
}

# --- Defaults ---
AI_MODE=false
CHECK_ONLY=false
SETUP=false
LAUNCH_CLAUDE=false
VERSION_SPEC="latest"
LAYERS="0,1,2,2ro,3,4,5"              # L6 needs a human, L7 needs an idle machine

# --- Output helpers (same shape as the Cloudflare runner) ---
timestamp() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
info()  { if $AI_MODE; then echo "[$(timestamp)] INFO: $1"; else echo "  $1"; fi }
pass()  { if $AI_MODE; then echo "[$(timestamp)] CHECK: PASS - $1"; else echo "  ✓ $1"; fi }
fail()  { if $AI_MODE; then echo "[$(timestamp)] CHECK: FAIL - $1"; else echo "  ✗ $1"; fi }
warn()  { if $AI_MODE; then echo "[$(timestamp)] WARN: $1"; else echo "  ⚠ $1"; fi }
error() { if $AI_MODE; then echo "[$(timestamp)] ERROR: $1" >&2; else echo "  ERROR: $1" >&2; fi }
step()  { if $AI_MODE; then echo "[$(timestamp)] START: $1"; else echo ""; echo "$1"; echo ""; fi }

header() {
    $AI_MODE && return 0
    echo ""
    echo "╭─────────────────────────────────────────────────────────────╮"
    echo "│  csa-google-workspace — conformance rig                     │"
    echo "│  runs the live suites GitHub Actions cannot                 │"
    echo "╰─────────────────────────────────────────────────────────────╯"
    echo ""
}

wants() { [[ ",$LAYERS," == *",$1,"* ]]; }

# --- Parse arguments ---
while [[ $# -gt 0 ]]; do
    case $1 in
        --ai)       AI_MODE=true; shift ;;
        --check)    CHECK_ONLY=true; shift ;;
        --setup)    SETUP=true; shift ;;
        --claude)   LAUNCH_CLAUDE=true; shift ;;
        --version)  VERSION_SPEC="$2"; shift 2 ;;
        --layers)   LAYERS="$2"; shift 2 ;;
        --folder)   export CSA_GW_TEST_FOLDER="$2"; shift 2 ;;
        --help|-h)
            sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "Unknown option: $1  (try --help)"; exit 1 ;;
    esac
done

mkdir -p "$RIG_DIR"

header

# --- Keep the checkout current: the live suites live only in git (spec §4) ---
if ! $CHECK_ONLY; then
    info "Pulling latest changes..."
    git -C "$SCRIPT_DIR" pull --quiet 2>/dev/null || warn "git pull failed (local changes, or not a git repo)"
fi

# =====================================================================
# Prerequisites
# =====================================================================
step "Checking prerequisites..."

PREREQ_OK=true
MISSING=0            # how many DesktopSetup-provided tools are absent

# The rig is specified as a Mac. Say so plainly rather than failing obscurely later.
case "$OS_KIND" in
    macos) pass "macOS" ;;
    windows)
        fail "Windows — this script is zsh and the rig is specified as a Mac (spec §6)"
        info "Run it under WSL, or use a Mac. DesktopSetup instructions for Windows:"
        desktop_setup_hint
        exit 1 ;;
    *)
        warn "$OS_KIND — the rig is specified as a Mac (spec §6); L7 will not work here"
        info "The API layers may still run. The editor layer needs macOS key handling." ;;
esac

check_cmd() {                                    # name, install-hint, required(true/false)
    if command -v "$1" &>/dev/null; then
        pass "$1 $("$1" --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1)"
    else
        if [[ "$3" == "false" ]]; then warn "$1 not installed — $2"; else
            fail "$1 not installed"; info "Install: $2"
            PREREQ_OK=false; MISSING=$((MISSING+1))
        fi
    fi
}

check_cmd python3 "brew install python3" true
check_cmd git     "xcode-select --install"  true
check_cmd gh      "brew install gh (then: gh auth login)" true
check_cmd pipx    "brew install pipx && pipx ensurepath" true

# Claude Code: the MCP surface is registered with it, and --claude triages failures.
export PATH="$HOME/.local/bin:$PATH"
if command -v claude &>/dev/null; then
    pass "Claude Code $(claude -v 2>/dev/null || echo unknown)"
else
    warn "Claude Code not installed — MCP registration and --claude are unavailable"
    MISSING=$((MISSING+1))
fi

# The plugin itself. DesktopSetup installs it, so its absence is the clearest single
# signal that DesktopSetup has not been run on this machine. Not fatal — this script
# installs the version under test itself — but worth saying, because everything ELSE
# DesktopSetup provides is probably missing too.
if command -v csa-google-workspace-mcp &>/dev/null; then
    # 2>&1 deliberately: this CLI prints to STDERR because stdout is the JSON-RPC
    # channel under stdio (cli.py — "stdout belongs to JSON-RPC"). Reading stdout here
    # would silently report an empty version.
    pass "csa-google-workspace plugin present ($(csa-google-workspace-mcp --version 2>&1 | head -1))"
else
    warn "csa-google-workspace plugin not installed — DesktopSetup has probably not been run"
    MISSING=$((MISSING+1))
fi

# Playwright is only needed for L7 (the editor layer), which is not in the default set.
if command -v playwright &>/dev/null; then
    pass "Playwright $(playwright --version 2>/dev/null | awk '{print $2}')"
else
    warn "Playwright not installed — L7 (editor conformance) cannot run"
    info "Install: pipx install playwright && playwright install chromium"
fi

if [[ $MISSING -gt 0 ]]; then
    echo ""
    if ! $AI_MODE; then
        echo "  ─────────────────────────────────────────────────────────────"
        echo "  $MISSING tool(s) missing. START WITH CSA DesktopSetup:"
        echo "  ─────────────────────────────────────────────────────────────"
    fi
    desktop_setup_hint
    info ""
    info "Then run this script again. Repo: $DESKTOP_SETUP_REPO"
fi

# =====================================================================
# Resolve the version under test  (spec §2)
# =====================================================================
step "Resolving the version under test..."

if [[ "$VERSION_SPEC" == "tree" ]]; then
    VERSION="$(cd "$SCRIPT_DIR" && python3 -c 'import re,pathlib; print(re.search(r"__version__ = \"([^\"]+)\"", pathlib.Path("src/csa_google_workspace/__init__.py").read_text()).group(1))')"
    pass "testing THIS CHECKOUT (version $VERSION) — explicitly requested"
elif [[ "$VERSION_SPEC" == "latest" ]]; then
    # A rig that silently tests the tree when PyPI is unreachable would report success
    # about a version nobody can install. So this is fatal, not a fallback.
    VERSION="$(python3 - <<'PY' 2>/dev/null || true
import json, urllib.request
with urllib.request.urlopen("https://pypi.org/pypi/csa-google-workspace/json", timeout=20) as r:
    print(json.load(r)["info"]["version"])
PY
)"
    if [[ -z "$VERSION" ]]; then
        fail "could not reach PyPI to resolve the latest version"
        info "Not falling back to the checkout — that would report success about a version nobody can install."
        info "Use --version tree deliberately, or --version X.Y.Z, if you meant to."
        exit 1
    fi
    pass "latest on PyPI: $VERSION"
else
    VERSION="$VERSION_SPEC"
    pass "pinned: $VERSION"
fi

# =====================================================================
# Install / upgrade  (spec §2, §9)
# =====================================================================
# Reinstall when the target differs from what is installed — which is also what makes a
# nightly run pick up a release cut since yesterday, without anyone passing --setup.
# Compare the version AND the KIND of install. They are separate questions and the version
# alone is not enough: a checkout and the wheel built from it share a version number, so
# switching to --version tree against a matching wheel would skip the reinstall entirely and
# the import assertion below would (correctly) refuse the run. Caught by that assertion.
INSTALLED="" ; INSTALLED_MODE=""
if [[ -x "$RIG_VENV/bin/python" ]]; then
    INSTALLED="$("$RIG_VENV/bin/python" -c \
        'import csa_google_workspace as w; print(w.__version__)' 2>/dev/null || true)"
    INSTALLED_MODE="$("$RIG_VENV/bin/python" -c \
        'import csa_google_workspace as w; print("wheel" if "site-packages" in w.__file__ else "tree")' \
        2>/dev/null || true)"
fi
[[ "$VERSION_SPEC" == "tree" ]] && WANT_MODE=tree || WANT_MODE=wheel

if $SETUP || [[ "$INSTALLED" != "$VERSION" || "$INSTALLED_MODE" != "$WANT_MODE" ]]; then
    step "Installing the artifact under test..."
    [[ -n "$INSTALLED" ]] && info "installed: $INSTALLED ($INSTALLED_MODE) -> wanted: $VERSION ($WANT_MODE)"

    rm -rf "$RIG_VENV"
    python3 -m venv "$RIG_VENV"
    "$RIG_VENV/bin/pip" install --quiet --upgrade pip

    if [[ "$VERSION_SPEC" == "tree" ]]; then
        "$RIG_VENV/bin/pip" install --quiet -e "${SCRIPT_DIR}[dev,mcp]"
        pass "installed the checkout (editable)"
    else
        # --no-cache-dir: pip's HTTP cache of the index page lives outside the venv, so a
        # fresh venv is NOT clean in the way that matters (RELEASING.md says so; ignoring
        # it cost minutes on 2026-09-05).
        # [dev] as well as [mcp]: the TESTS need dependencies the wheel does not carry
        # (PyYAML, for one - tests/test_release_workflow_shape.py parses release.yml).
        # Taking dev from PyPI at the same version keeps every piece version-matched.
        "$RIG_VENV/bin/pip" install --quiet --no-cache-dir "${PKG}[mcp,dev]==$VERSION"
        pass "installed ${PKG}[mcp]==$VERSION from PyPI"
    fi

    # The console script, installed the way a USER installs it — this is what the MCP
    # client launches, so it must be the isolated app install, not the rig venv.
    if command -v pipx &>/dev/null; then
        if [[ "$VERSION_SPEC" == "tree" ]]; then
            pipx install --force "${SCRIPT_DIR}[mcp]" >/dev/null 2>&1 && pass "pipx: installed from the checkout" \
                || warn "pipx install from the checkout failed"
        else
            pipx install --force "${PKG}[mcp]==$VERSION" >/dev/null 2>&1 && pass "pipx: $PKG==$VERSION" \
                || warn "pipx install failed — the MCP layers may use a stale console script"
        fi
    fi
fi

# =====================================================================
# THE ANTI-LIE GUARD  (spec §3) — the most important check in this script
# =====================================================================
step "Proving what is actually under test..."

# pyproject sets pythonpath = ["src"], so a naive pytest run imports the CHECKOUT even
# with a wheel installed. Every pytest invocation below passes -o pythonpath= , and this
# asserts the result before anything is allowed to run.
IMPORT_CHECK="$("$RIG_VENV/bin/python" - "$VERSION" "$VERSION_SPEC" 2>&1 <<'PY'
import sys
import csa_google_workspace as w
want, spec = sys.argv[1], sys.argv[2]
is_wheel = "site-packages" in w.__file__
print(f"path={w.__file__}")
print(f"version={w.__version__}")
if w.__version__ != want:
    print(f"MISMATCH: imported {w.__version__}, expected {want}"); sys.exit(1)
if spec == "tree":
    if is_wheel: print("MISMATCH: --version tree but imported an installed wheel"); sys.exit(1)
elif not is_wheel:
    print("MISMATCH: expected the installed wheel, imported the working tree"); sys.exit(1)
print("OK")
PY
)" || { error "import check FAILED:"; echo "$IMPORT_CHECK"; exit 1; }

echo "$IMPORT_CHECK" | grep -q '^OK$' || { error "import check FAILED:"; echo "$IMPORT_CHECK"; exit 1; }
pass "imported $(echo "$IMPORT_CHECK" | grep '^path=' | cut -d= -f2-)"
pass "version $VERSION confirmed — not shadowed by the checkout"

# =====================================================================
# MCP registration  (what the user asked about)
# =====================================================================
if command -v claude &>/dev/null; then
    step "Checking MCP registration with Claude Code..."
    if claude mcp list 2>/dev/null | grep -q "$PKG"; then
        pass "registered with Claude Code"
    elif $SETUP; then
        if claude mcp add -s user "$PKG" -- csa-google-workspace-mcp >/dev/null 2>&1; then
            pass "registered with Claude Code (added)"
        else
            warn "could not register — add it by hand:"
            info "claude mcp add -s user $PKG -- csa-google-workspace-mcp"
        fi
    else
        warn "not registered with Claude Code — re-run with --setup, or:"
        info "claude mcp add -s user $PKG -- csa-google-workspace-mcp"
    fi
fi

# =====================================================================
# Credentials — present AND live  (spec §6)
# =====================================================================
step "Checking credentials..."

CREDS_RW_OK=false
CREDS_RO_OK=false

if [[ -f "$CLIENT_SECRETS" ]]; then
    pass "OAuth client secrets present"
else
    fail "OAuth client secrets not found at $CLIENT_SECRETS"
    info "It is a DESKTOP-APP client, and it lives in the private CSA-Plugins repo."
    info "Put it there, or set CSA_GW_CLIENT_SECRETS."
    PREREQ_OK=false
fi

# Presence is not liveness. A real API call, using the package under test — which also
# proves the wheel's auth path works, not just that a file exists on disk.
probe_token() {                                   # $1 = "rw" | "ro"
    "$RIG_VENV/bin/python" - "$1" <<'PY' 2>/dev/null
import os, sys
from googleapiclient.discovery import build
from csa_google_workspace.auth import load_cached_credentials
ro = sys.argv[1] == "ro"
path = os.path.expanduser(
    os.environ.get("CSA_GW_TOKEN", "~/.csa_google_workspace/token.json"))
creds = load_cached_credentials(path, read_only=ro)
me = build("drive", "v3", credentials=creds).about().get(
    fields="user(emailAddress)").execute()["user"]["emailAddress"]
print(me)
PY
}

if [[ -f "$TOKEN_RW" ]]; then
    ACCOUNT="$(probe_token rw || true)"
    if [[ -n "$ACCOUNT" ]]; then
        pass "read-write token is LIVE (account: $ACCOUNT)"
        CREDS_RW_OK=true
    else
        fail "read-write token present but not usable — expired, revoked, or wrong client"
        info "Re-authorize: csa-google-workspace-mcp login --force"
    fi
else
    fail "no read-write token at $TOKEN_RW"
    info "Authorize: csa-google-workspace-mcp login"
fi

# The read-only posture has its OWN cache and needs its OWN consent (spec §5a/§6).
# Not being set up is a real gap, not an inconvenience: L2-RO is the only layer that
# proves read-only is refused by GOOGLE rather than by our own client guard.
if [[ -f "$TOKEN_RO" ]]; then
    if [[ -n "$(CSA_GW_READ_ONLY=1 probe_token ro || true)" ]]; then
        pass "read-only token is LIVE (separate consent, as designed)"
        CREDS_RO_OK=true
    else
        fail "read-only token present but not usable"
        info "Re-authorize: CSA_GW_READ_ONLY=1 csa-google-workspace-mcp login --force"
    fi
else
    warn "no read-only token — L2-RO will be SKIPPED"
    info "Set it up (a separate consent, on purpose):"
    info "  CSA_GW_READ_ONLY=1 csa-google-workspace-mcp login"
fi

# Where the live layers will create files. Loose in My Drive root is the wrong answer for
# something running unattended; the suite defaults to a dated folder it removes afterwards.
if [[ -n "$CSA_GW_TEST_FOLDER" ]]; then
    pass "test files -> your folder $CSA_GW_TEST_FOLDER (kept, never trashed by a run)"
else
    info "test files -> a dated folder, created per run and trashed at the end"
    info "  --folder <id|url> to use a standing folder you can inspect instead"
fi

echo ""
if ! $PREREQ_OK; then
    if $AI_MODE; then echo "[$(timestamp)] COMPLETE: prerequisites missing"; else
        echo "✗ Some prerequisites are missing — fix the above and re-run."; fi
    exit 1
fi
$AI_MODE && echo "[$(timestamp)] COMPLETE: prerequisites met" || echo "✓ Prerequisites met"

if $CHECK_ONLY; then exit 0; fi

# =====================================================================
# The layers  (spec §5)
# =====================================================================
PY_BIN="$RIG_VENV/bin/python"
RESULTS=()
FAILED=0
: > "$RUN_LOG"

run_layer() {                                     # id, description, command...
    local id="$1" desc="$2"; shift 2
    wants "$id" || return 0
    step "L$id — $desc"
    {
        echo "───────── L$id — $desc"
        echo "\$ $*"
    } >> "$RUN_LOG"
    if "$@" >>"$RUN_LOG" 2>&1; then
        pass "L$id passed"; RESULTS+=("L$id PASS")
    else
        fail "L$id FAILED (see $RUN_LOG)"; RESULTS+=("L$id FAIL"); FAILED=$((FAILED+1))
    fi
}

cd "$SCRIPT_DIR"

# -o pythonpath= on every invocation: without it the checkout shadows the wheel (§3).
run_layer 1 "offline unit suite" \
    "$PY_BIN" -m pytest -q -o pythonpath= tests/ \
        --ignore=tests/integration --ignore=tests/oauth

if $CREDS_RW_OK; then
    run_layer 2 "live integration suite — FULL READ/WRITE" \
        env CSA_GW_INTEGRATION=1 CSA_GW_CLIENT_SECRETS="$CLIENT_SECRETS" \
        CSA_GW_TEST_FOLDER="$CSA_GW_TEST_FOLDER" \
        "$PY_BIN" -m pytest -q -o pythonpath= tests/integration/
else
    wants 2 && { warn "L2 skipped — no live read-write token"; RESULTS+=("L2 SKIP"); }
fi

# L2-RO: proves read-only is refused by GOOGLE, not by our client guard (spec §5a).
# The test file does not exist yet — say so rather than silently passing.
if wants 2ro; then
    if [[ ! -f tests/integration/test_read_only_is_enforced_by_google.py ]]; then
        warn "L2-RO NOT BUILT YET — see spec §5a. Nothing today proves the read-only"
        info "token cannot write; existing coverage stops at the client guard."
        RESULTS+=("L2-RO NOT-BUILT")
    elif ! $CREDS_RO_OK; then
        warn "L2-RO skipped — no read-only token"; RESULTS+=("L2-RO SKIP")
    else
        run_layer 2ro "prove read-only is enforced by Google" \
            env CSA_GW_INTEGRATION=1 CSA_GW_READ_ONLY=1 CSA_GW_CLIENT_SECRETS="$CLIENT_SECRETS" \
            "$PY_BIN" -m pytest -q -o pythonpath= \
            tests/integration/test_read_only_is_enforced_by_google.py
    fi
fi

run_layer 3 "MCP server smoke" "$PY_BIN" scripts/mcp_smoke.py

if $CREDS_RW_OK; then
    run_layer 4 "zoo verification (read-only against the specimens)" \
        "$PY_BIN" experiments/zoo/verify.py
    run_layer 5 "guided demo — the end-to-end" \
        "$RIG_VENV/bin/csa-google-workspace-mcp" demo --auto
else
    wants 4 && { warn "L4 skipped — no live token"; RESULTS+=("L4 SKIP"); }
    wants 5 && { warn "L5 skipped — no live token"; RESULTS+=("L5 SKIP"); }
fi

# =====================================================================
# Summary
# =====================================================================
step "Results"
for r in "${RESULTS[@]}"; do
    case "$r" in
        *PASS)  pass "$r" ;;
        *FAIL)  fail "$r" ;;
        *)      warn "$r" ;;
    esac
done
echo ""
info "version under test : $VERSION ($VERSION_SPEC)"
info "full log           : $RUN_LOG"

if [[ $FAILED -gt 0 ]]; then
    if $AI_MODE; then echo "[$(timestamp)] COMPLETE: $FAILED layer(s) failed"; else
        echo ""; echo "✗ $FAILED layer(s) failed."; fi
else
    if $AI_MODE; then echo "[$(timestamp)] COMPLETE: all layers passed"; else
        echo ""; echo "✓ All requested layers passed."; fi
fi

# =====================================================================
# Hand off to Claude Code to triage and file  (spec §8)
# =====================================================================
if $LAUNCH_CLAUDE && command -v claude &>/dev/null; then
    PROMPT="You are triaging a conformance-rig run of csa-google-workspace.

Version under test: $VERSION (requested: $VERSION_SPEC)
Results: ${RESULTS[*]}
Full log: $RUN_LOG

Read docs/superpowers/specs/2026-09-05-conformance-rig.md section 8 before filing anything.

Your job:
1. Read the log and work out what ACTUALLY failed. A layer can fail for its own reasons
   (an expired token, a network blip) rather than a real defect - say which it is.
2. For each genuine failure, check whether an issue is already open for it. Fingerprint on
   (layer, test id, first line of the assertion). If one exists, COMMENT that it reproduced
   on $VERSION rather than opening a second issue.
3. REDACT before anything reaches GitHub. pytest output can contain Drive file ids, document
   titles, comment text and email addresses. A file id in a public issue is a working link to
   the document. Environment facts should come from _environment.describe_environment(),
   which is already written to be safe for a public tracker.
4. Include: the version under test, proof of what was imported (the path assertion), which
   layer, the test id, and the exact command to reproduce.

Do not open an issue for a layer marked SKIP or NOT-BUILT - those are setup state, not defects.
Be concise, and ask before filing anything."
    echo ""
    info "Launching Claude Code to triage..."
    cd "$SCRIPT_DIR"
    exec claude "$PROMPT"
fi

[[ $FAILED -gt 0 ]] && exit 1
exit 0
