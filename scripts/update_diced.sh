#!/usr/bin/env bash
set -euo pipefail

# Update or bootstrap local DICED integration checkout.
# - Clones when repo folder is missing.
# - Pulls --ff-only when it is already a git checkout.
# - Refuses to overwrite a non-git folder unless --force-reclone is used.

REPO_URL="https://github.com/RalfKliemt/DICED.git"
TARGET_DIR="data/integrations/diced/repo"
FORCE_RECLEAN=0

if [[ "${1:-}" == "--force-reclone" ]]; then
  FORCE_RECLEAN=1
fi

if [[ ! -d "$TARGET_DIR" ]]; then
  mkdir -p "$(dirname "$TARGET_DIR")"
  echo "[diced] Cloning into $TARGET_DIR"
  git clone --depth 1 "$REPO_URL" "$TARGET_DIR"
  echo "[diced] Clone complete"
  exit 0
fi

if git -C "$TARGET_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "[diced] Existing git checkout found, pulling latest changes"
  git -C "$TARGET_DIR" pull --ff-only
  echo "[diced] Update complete"
  exit 0
fi

if [[ "$FORCE_RECLEAN" -eq 1 ]]; then
  echo "[diced] Non-git folder found, replacing with fresh clone"
  rm -rf "$TARGET_DIR"
  mkdir -p "$(dirname "$TARGET_DIR")"
  git clone --depth 1 "$REPO_URL" "$TARGET_DIR"
  echo "[diced] Reclone complete"
  exit 0
fi

echo "[diced] $TARGET_DIR exists but is not a git checkout."
echo "[diced] Use --force-reclone to replace it with a fresh clone."
exit 0
