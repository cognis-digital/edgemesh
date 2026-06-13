#!/usr/bin/env sh
# edgemesh installer for Linux & macOS.
# Installs the `edgemesh` CLI from the current checkout (or a git URL).
# Prefers pipx (isolated), falls back to a user venv. Pure POSIX sh.
set -eu

REPO_URL="${EDGEMESH_REPO:-https://github.com/cognis-digital/edgemesh.git}"
SRC="."
# If not run from a checkout, install straight from git.
[ -f "./pyproject.toml" ] && grep -q 'name = "edgemesh"' ./pyproject.toml 2>/dev/null || SRC="git+${REPO_URL}"

PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "error: Python 3.10+ is required but not found on PATH." >&2
  exit 1
fi
echo "edgemesh installer — using $($PY --version 2>&1) from $PY"
echo "source: $SRC"

if command -v pipx >/dev/null 2>&1; then
  echo "-> installing with pipx (isolated)"
  pipx install --force "$SRC"
else
  echo "-> pipx not found; installing into a user venv at ~/.edgemesh-venv"
  "$PY" -m venv "$HOME/.edgemesh-venv"
  # shellcheck disable=SC1091
  . "$HOME/.edgemesh-venv/bin/activate"
  python -m pip install --upgrade pip >/dev/null
  python -m pip install "$SRC"
  BIN="$HOME/.edgemesh-venv/bin/edgemesh"
  # symlink into a dir that's commonly on PATH
  for d in "$HOME/.local/bin" "/usr/local/bin"; do
    if [ -d "$d" ] && [ -w "$d" ]; then ln -sf "$BIN" "$d/edgemesh"; echo "linked -> $d/edgemesh"; break; fi
  done
  echo "If 'edgemesh' isn't found, add this to your shell profile:"
  echo "  export PATH=\"\$HOME/.edgemesh-venv/bin:\$PATH\""
fi

echo
echo "Installed. Next steps:"
echo "  edgemesh setup     # guided setup"
echo "  edgemesh menu      # interactive menu"
echo "  edgemesh serve     # run the gateway"
