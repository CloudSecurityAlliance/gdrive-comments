#!/bin/zsh
#
# Setup-test-machine.sh
#
# ONE-TIME setup of a dedicated macOS conformance machine.
# Spec: docs/superpowers/specs/2026-09-05-conformance-rig.md
#
# This is the setup you do once. `Run-full-test-suite.sh` is the thing you run afterwards,
# nightly or whenever, and it needs no human. THIS script does — it opens a browser twice
# for Google consent, and there is no way around that.
#
# Usage:
#   ./Setup-test-machine.sh              # do it
#   ./Setup-test-machine.sh --check      # report what is missing, change nothing
#   ./Setup-test-machine.sh --ai         # machine-readable timestamped output
#   ./Setup-test-machine.sh --debug      # trace every command to ~/.csa_gw_rig/setup-debug.log
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PKG="csa-google-workspace"
CONFIG_DIR="$HOME/.csa_google_workspace"
CLIENT_SECRETS="${CSA_GW_CLIENT_SECRETS:-$CONFIG_DIR/client_secret.json}"
TOKEN_RW="${CSA_GW_TOKEN:-$CONFIG_DIR/token.json}"
TOKEN_RO="$CONFIG_DIR/token.readonly.json"
DESKTOP_SETUP_REPO="https://github.com/CloudSecurityAlliance/DesktopSetup"
SECRETS_REPO="CloudSecurityAlliance-Internal/CSA-Plugins"

AI_MODE=false
CHECK_ONLY=false
DEBUG=false

timestamp() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
info()  { if $AI_MODE; then echo "[$(timestamp)] INFO: $1"; else echo "  $1"; fi }
pass()  { if $AI_MODE; then echo "[$(timestamp)] CHECK: PASS - $1"; else echo "  ✓ $1"; fi }
fail()  { if $AI_MODE; then echo "[$(timestamp)] CHECK: FAIL - $1"; else echo "  ✗ $1"; fi }
warn()  { if $AI_MODE; then echo "[$(timestamp)] WARN: $1"; else echo "  ⚠ $1"; fi }
step()  { if $AI_MODE; then echo "[$(timestamp)] START: $1"; else echo ""; echo "$1"; echo ""; fi }

while [[ $# -gt 0 ]]; do
    case $1 in
        --ai)    AI_MODE=true; shift ;;
        --check) CHECK_ONLY=true; shift ;;
        --debug) DEBUG=true; shift ;;
        --help|-h) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $1 (try --help)"; exit 1 ;;
    esac
done

if ! $AI_MODE; then
    echo ""
    echo "╭─────────────────────────────────────────────────────────────╮"
    echo "│  csa-google-workspace — set up a conformance machine        │"
    echo "│  one-time. opens a browser twice. then you never touch it.  │"
    echo "╰─────────────────────────────────────────────────────────────╯"
fi

TODO=0

# --debug traces to a FILE, not the terminal: the failures worth debugging here are pip and
# brew output, and interleaving a shell trace with them makes both unreadable.
DEBUG_LOG=""
if $DEBUG; then
    mkdir -p "$HOME/.csa_gw_rig"
    DEBUG_LOG="$HOME/.csa_gw_rig/setup-debug.log"
    : > "$DEBUG_LOG"
    exec 4>>"$DEBUG_LOG"; export BASH_XTRACEFD=4
    setopt XTRACE 2>/dev/null || set -x
fi

# =====================================================================
# 1. The machine
# =====================================================================
step "1. The machine"

if [[ "$(uname -s)" != "Darwin" ]]; then
    fail "not macOS. The editor layer is ⌘-based and the rig is specified as a Mac (spec §6)."
    info "Windows/Linux setup: $DESKTOP_SETUP_REPO"
    exit 1
fi
pass "macOS $(sw_vers -productVersion 2>/dev/null)"

# The rig's browser layer cannot share a keyboard with a person (measured 2026-09-03: focus
# moves mid-sequence and keystrokes land elsewhere). Worth saying once, here, plainly.
info "This machine should be DEDICATED — the editor layer breaks if somebody is using it."

MISSING_TOOLS=()

# Python by VERSION, not existence (#440): macOS ships 3.9.6 at /usr/bin/python3 and this
# needs >= 3.10, so a bare `command -v` passes and the failure surfaces much later as an
# unreadable pip resolver dump. Search for a newer one first — a Mac often has both.
PYTHON=""
for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
    command -v "$candidate" &>/dev/null || continue
    if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
        PYTHON="$(command -v "$candidate")"; break
    fi
done
if [[ -n "$PYTHON" ]]; then
    pass "python $("$PYTHON" -c 'import platform; print(platform.python_version())') ($PYTHON)"
else
    if command -v python3 &>/dev/null; then
        fail "python3 is $(python3 -c 'import platform; print(platform.python_version())' 2>/dev/null); this needs >= 3.10"
        info "macOS ships 3.9 at /usr/bin/python3 — DesktopSetup installs a newer one."
    else
        fail "no python3"
    fi
    MISSING_TOOLS+=(python3)
fi

for t in git gh pipx; do
    command -v "$t" &>/dev/null && pass "$t" || { fail "$t"; MISSING_TOOLS+=("$t"); }
done
export PATH="$HOME/.local/bin:$PATH"
command -v claude &>/dev/null && pass "claude" || { fail "claude"; MISSING_TOOLS+=(claude); }

if (( ${#MISSING_TOOLS[@]} )); then
    warn "${#MISSING_TOOLS[@]} tool(s) missing. Run CSA DesktopSetup — it installs all of them:"
    info "  bash -c \"\$(curl -fsSL -H 'Cache-Control: no-cache' \\"
    info "    https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-ai-tools.sh)\""
    info "Then run this script again."
    exit 1
fi

# =====================================================================
# 2. The claude.ai Google Drive connector must not be live
# =====================================================================
step "2. Conflicting Drive connectors"

# Why this matters enough to be step 2: a hosted Drive connector in the same session can
# answer a question meant for THIS server — the run goes green having never exercised the
# library — and it defeats the policy ceiling, which binds our calls and not another
# client's. See .claude/README.md.
if [[ -f "$SCRIPT_DIR/.claude/settings.json" ]] \
   && grep -q "mcp__claude_ai_Google_Drive" "$SCRIPT_DIR/.claude/settings.json"; then
    pass "this repo denies the claude.ai Google Drive connector (.claude/settings.json)"
else
    fail ".claude/settings.json does not deny mcp__claude_ai_Google_Drive*"
    TODO=$((TODO+1))
fi

CONNECTOR_STATE="$(claude mcp list 2>&1 | head -1)"
if echo "$CONNECTOR_STATE" | grep -q "claude.ai connectors are disabled"; then
    pass "claude.ai connectors are not loading on this machine at all"
elif claude mcp list 2>&1 | grep -qiE "google.?drive|google.?workspace" \
     && ! claude mcp list 2>&1 | grep -q "^csa-google-workspace"; then
    warn "a Google Drive connector appears to be live"
    info "The repo setting above blocks it for sessions started IN this directory."
    info "To remove it account-wide: claude.ai -> Settings -> Connectors -> Google Drive."
else
    pass "no conflicting Drive connector visible"
fi

# =====================================================================
# 3. The package
# =====================================================================
step "3. The package and its MCP registration"

if $CHECK_ONLY; then
    command -v csa-google-workspace-mcp &>/dev/null \
        && pass "$PKG installed ($(csa-google-workspace-mcp --version 2>&1 | head -1))" \
        || { fail "$PKG not installed"; TODO=$((TODO+1)); }
else
    pipx install --force "${PKG}[mcp]" >/dev/null 2>&1 \
        && pass "$PKG installed via pipx ($(csa-google-workspace-mcp --version 2>&1 | head -1))" \
        || { fail "pipx install failed"; TODO=$((TODO+1)); }
fi

if claude mcp list 2>/dev/null | grep -q "^$PKG"; then
    pass "registered with Claude Code"
elif ! $CHECK_ONLY; then
    claude mcp add -s user "$PKG" -- csa-google-workspace-mcp >/dev/null 2>&1 \
        && pass "registered with Claude Code" || { warn "registration failed; add by hand:"
        info "claude mcp add -s user $PKG -- csa-google-workspace-mcp"; }
else
    fail "not registered with Claude Code"; TODO=$((TODO+1))
fi

# =====================================================================
# 4. The OAuth client — the one credential-bearing artifact
# =====================================================================
step "4. The OAuth client"

if [[ -f "$CLIENT_SECRETS" ]]; then
    pass "client secrets present at $CLIENT_SECRETS"
else
    fail "no client secrets at $CLIENT_SECRETS"
    info "It must be a DESKTOP-APP OAuth client. Google's API ToS forbid shipping developer"
    info "credentials in an open-source project, so it lives in the PRIVATE repo:"
    info "  $SECRETS_REPO"
    info "Put it at $CLIENT_SECRETS, or set CSA_GW_CLIENT_SECRETS."
    TODO=$((TODO+1))
fi

# =====================================================================
# 5. Two logins — and two is the point, not an annoyance
# =====================================================================
step "5. Google authorization (browser opens — twice)"

# The read-only posture caches its consent SEPARATELY (token.readonly.json) and a read-write
# token deliberately does not satisfy it. That separation is the property L2-RO tests: if the
# read-only posture could ever be served from the read-write cache, that IS the #327 failure.
if [[ -f "$TOKEN_RW" ]]; then
    pass "read-write token present"
elif $CHECK_ONLY; then
    fail "no read-write token"; TODO=$((TODO+1))
elif [[ -f "$CLIENT_SECRETS" ]]; then
    info "Opening a browser for the READ-WRITE consent..."
    csa-google-workspace-mcp login && pass "read-write token cached" \
        || { fail "read-write login failed"; TODO=$((TODO+1)); }
fi

if [[ -f "$TOKEN_RO" ]]; then
    pass "read-only token present (separate consent, as designed)"
elif $CHECK_ONLY; then
    fail "no read-only token — L2-RO cannot run"; TODO=$((TODO+1))
elif [[ -f "$CLIENT_SECRETS" ]]; then
    info "Opening a browser for the READ-ONLY consent. This is a SECOND, separate grant:"
    info "a read-write token does not satisfy it, and that separation is what L2-RO tests."
    CSA_GW_READ_ONLY=1 csa-google-workspace-mcp login && pass "read-only token cached" \
        || { fail "read-only login failed"; TODO=$((TODO+1)); }
fi

# =====================================================================
# 6. Playwright, for the editor layer
# =====================================================================
step "6. Playwright (editor conformance, L7)"

if command -v playwright &>/dev/null; then
    pass "playwright $(playwright --version 2>/dev/null | awk '{print $2}')"
    if ! $CHECK_ONLY; then
        playwright install chromium >/dev/null 2>&1 && pass "chromium installed" \
            || warn "chromium install failed — L7 will not run"
    fi
elif $CHECK_ONLY; then
    warn "playwright not installed — L7 (editor conformance) cannot run"
else
    pipx install playwright >/dev/null 2>&1 && playwright install chromium >/dev/null 2>&1 \
        && pass "playwright + chromium installed" || warn "playwright install failed"
fi

# =====================================================================
# Done
# =====================================================================
step "Result"

if [[ $TODO -gt 0 ]]; then
    fail "$TODO thing(s) still to do — see above"
    info "Re-run this script once you have fixed them."
    exit 1
fi

pass "setup complete"
info ""
info "Now verify, then run for real:"
info "  ./Run-full-test-suite.sh --check      # prerequisites only"
info "  ./Run-full-test-suite.sh              # latest PyPI release, all unattended layers"
info ""
info "To run it nightly, see the launchd note in"
info "  docs/superpowers/specs/2026-09-05-conformance-rig.md"
info ""
info "If something is wrong, generate a report to attach to an issue:"
info "  ./Run-full-test-suite.sh --check --report"
[[ -n "$DEBUG_LOG" ]] && info "command trace: $DEBUG_LOG"
