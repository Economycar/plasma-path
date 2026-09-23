#!/usr/bin/env bash
# Package a numbered release of the skill and tag it in git.
#   skill/release.sh            -> checks versions agree, packages dist/plasma-path-<ver>.skill, tags skill-v<ver>
# Bump the version first in scripts/pp.py, SKILL.md (metadata.version) and CHANGELOG.md.
set -euo pipefail
cd "$(dirname "$0")"
VER=$(python3 -c "import re;print(re.search(r'__version__ = \"([^\"]+)\"', open('plasma-path/scripts/pp.py').read()).group(1))")
SKV=$(python3 -c "import re;print(re.search(r'version: \"([^\"]+)\"', open('plasma-path/SKILL.md').read()).group(1))")
grep -q "^## $VER " plasma-path/CHANGELOG.md || { echo "CHANGELOG.md has no entry for $VER"; exit 1; }
[ "$VER" = "$SKV" ] || { echo "version mismatch: pp.py $VER vs SKILL.md $SKV"; exit 1; }
SKILL_DIR="$(pwd)/plasma-path"
SC=$(ls -d ~/.claude/skills/synced/*/skill-creator 2>/dev/null | head -1)
if [ -n "$SC" ]; then (cd "$SC" && python3 -m scripts.quick_validate "$SKILL_DIR" | tail -1); fi
OUT=dist/plasma-path-$VER.skill
rm -f "$OUT"
(cd . && zip -qr "$OUT" plasma-path -x '*__pycache__*' '*.pyc' 'plasma-path/evals/*')
echo "packaged $OUT ($(du -h "$OUT" | cut -f1))"
if git -C .. rev-parse --git-dir >/dev/null 2>&1; then
  if git -C .. rev-parse "skill-v$VER" >/dev/null 2>&1; then
    echo "tag skill-v$VER already exists; commit your changes and bump the version for a new release"
  else
    echo "next: git add -A && git commit -m 'skill $VER' && git tag skill-v$VER"
  fi
fi
