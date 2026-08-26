"""Write a working Claude Desktop config, because the user should not have to. (D2)

**The failure is a `PATH` fact, not a bug, and it looks like a bug.** Claude Desktop is a GUI
app, so on macOS it inherits launchd's `PATH` — `/usr/bin:/bin:/usr/sbin:/sbin`. That contains
neither `~/.local/bin`, where `pipx` puts the console script, nor Homebrew; and the `python3` it
*does* contain is macOS's system 3.9, below this package's 3.10 floor. So a bare command name is
not found and `python3` is the wrong interpreter. Claude Code, running in your shell, works
perfectly — which is exactly why this reads as "Desktop is broken" rather than "GUI apps have a
different environment".

The README has documented the fix for months: put the absolute path in the config. That is a
workaround with a hand-edit in it — the user has to know their own home directory, produce valid
JSON, and not clobber the other servers already in that file. **Half the intended clients are
Desktop.** So the tool writes it: it knows its own absolute path, which is the one piece of
information the user was being asked to supply.

The second half, hit immediately after the first: **Desktop has no shell**, so the policy
variables that work in a terminal are simply absent there. The `env` block is the only place
Desktop reads them, so `configure` carries the `CSA_GW_*` variables across — and *only* those,
because it is reading an ambient environment that also holds cloud keys and tokens, into a file
somebody may well screenshot when asking for help.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

SERVER_KEY = "csa-google-workspace"
SCRIPT_NAME = "csa-google-workspace-mcp"

# Carried into the config, because Desktop has no shell to read them from. `CSA_GW_CLIENT_SECRETS`
# is deliberately NOT here: `login` needs it and the running server never does, because a cached
# token carries its own client id and secret. Writing a credential path into a shared config file
# spreads it for no benefit.
CARRIED_PREFIX = "CSA_GW_"
NOT_CARRIED = frozenset({"CSA_GW_CLIENT_SECRETS"})


@dataclass
class Result:
    path: Path
    rendered: str
    created: bool
    backup: Path | None
    changed: bool


def config_path(env: Mapping[str, str] | None = None) -> Path:
    """Where Claude Desktop keeps its config on this platform."""
    env = os.environ if env is None else env
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    if sys.platform.startswith("win"):
        base = env.get("APPDATA") or str(Path.home() / "AppData/Roaming")
        return Path(base) / "Claude/claude_desktop_config.json"
    # Linux Desktop is not a shipped target; returning the XDG-ish location is more useful
    # than raising, because `--print` still shows somebody the right JSON to paste.
    return Path.home() / ".config/Claude/claude_desktop_config.json"


def launch_command() -> tuple[list[str], str]:
    """(argv, how it was resolved) — always absolute, never a bare name.

    Three sources, in order of how self-contained the result is:

    1. The console script **beside the running interpreter**. In a `pipx` or venv install this
       is the whole answer: the script's shebang pins the correct Python, so the config needs
       no interpreter and no `PATH`.
    2. The console script anywhere on the *current* `PATH`, resolved to absolute. Correct, and
       one step less certain, because it may not be the install this process came from.
    3. `sys.executable -m csa_google_workspace.mcp`. Always available and always right about
       the interpreter — `sys.executable` is absolute by construction — which is what makes it
       a real fallback rather than a guess.
    """
    beside = Path(sys.executable).parent / SCRIPT_NAME
    if beside.exists():
        return [str(beside)], "the console script beside this interpreter"
    found = shutil.which(SCRIPT_NAME)
    if found:
        return [str(Path(found).resolve())], f"{SCRIPT_NAME} on PATH"
    return [sys.executable, "-m", "csa_google_workspace.mcp"], "this interpreter, with -m"


def carried_env(env: Mapping[str, str]) -> dict[str, str]:
    return {k: v for k, v in sorted(env.items())
            if k.startswith(CARRIED_PREFIX) and k not in NOT_CARRIED}


def entry(env: Mapping[str, str]) -> dict:
    command, _ = launch_command()
    out: dict = {"command": command[0]}
    if len(command) > 1:
        out["args"] = command[1:]
    carried = carried_env(env)
    if carried:
        out["env"] = carried
    return out


def configure(path: Path | None = None, *, env: Mapping[str, str] | None = None,
              dry_run: bool = False) -> Result:
    """Merge this server into Claude Desktop's config, preserving everything else.

    Raises `ValueError` on unreadable JSON rather than replacing it: a file that does not parse
    is most likely one somebody is part-way through editing, and the cost of being wrong about
    that is their other servers.
    """
    env = os.environ if env is None else env
    path = config_path(env) if path is None else Path(path)

    existing: dict = {}
    created = not path.exists()
    if not created:
        try:
            existing = json.loads(path.read_text() or "{}")
        except json.JSONDecodeError as e:
            raise ValueError(
                f"{path} is not valid JSON ({e}), so it has not been touched. Fix or move it "
                f"and run this again - replacing it would remove any other MCP servers "
                f"configured there.") from e
        if not isinstance(existing, dict):
            raise ValueError(f"{path} could not be read as a JSON object, so it was left alone")

    servers = dict(existing.get("mcpServers") or {})
    wanted = entry(env)
    changed = servers.get(SERVER_KEY) != wanted
    servers[SERVER_KEY] = wanted
    merged = {**existing, "mcpServers": servers}
    rendered = json.dumps(merged, indent=2) + "\n"

    if dry_run:
        return Result(path=path, rendered=rendered, created=created, backup=None, changed=changed)

    backup = None
    if not created and changed:
        # Timestamped rather than a single `.bak`, so a second run cannot destroy the copy of
        # the file the user actually hand-wrote.
        backup = path.with_suffix(path.suffix + f".bak.{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(path, backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered)
    return Result(path=path, rendered=rendered, created=created, backup=backup, changed=changed)
