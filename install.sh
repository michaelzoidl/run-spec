#!/usr/bin/env bash
# Symlink this skill into ~/.claude/skills/run-spec so every Claude Code
# session on this machine can use it. Re-run after pulling.
set -euo pipefail

src="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dest="$HOME/.claude/skills/run-spec"

if [ -e "$dest" ] && [ ! -L "$dest" ]; then
  echo "refusing to replace $dest — it exists and is not a symlink." >&2
  echo "Move it aside first if you want this checkout to take over." >&2
  exit 1
fi

mkdir -p "$HOME/.claude/skills"
ln -sfn "$src" "$dest"
chmod +x "$src/scripts/runspec.py"

echo "linked $dest -> $src"
echo "try:  /run-spec path/to/SPEC.md"
