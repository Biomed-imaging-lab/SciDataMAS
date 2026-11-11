#!/usr/bin/env bash
# Install the SciDataMAS plugin into a local DSH Web profile without pnpm.
#
# Usage:
#   ./scripts/install-local.sh
#   DSH_HOME=/path/to/.dsh DSH_PROFILE=web SCIDATAMAS_ROOT=/data/lake ./scripts/install-local.sh
#
# The script:
#   1. symlinks this repository into <profile>/node_modules/scidatamas-dsh-plugin;
#   2. adds one `insert` row to <profile>/cordis.patch.yml (with a backup);
#   3. creates the lake root;
#   4. prints the restart/verification steps.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DSH_HOME="${DSH_HOME:-$HOME/.dsh}"
DSH_PROFILE="${DSH_PROFILE:-web}"
PROFILE_DIR="$DSH_HOME/profiles/$DSH_PROFILE"
PACKAGE_LINK="$PROFILE_DIR/node_modules/scidatamas-dsh-plugin"
PATCH="$PROFILE_DIR/cordis.patch.yml"
DATA_ROOT="${SCIDATAMAS_ROOT:-$HOME/data/scidatamas}"

if [ ! -d "$PROFILE_DIR" ]; then
  echo "Profile not found: $PROFILE_DIR" >&2
  echo "Start the DSH Web profile once so it creates the profile, then rerun this script." >&2
  echo "Example: npx -y @deepseek-ai/dsh@0.2.2-rc.1 --profile $DSH_PROFILE web" >&2
  exit 1
fi

mkdir -p "$PROFILE_DIR/node_modules" "$DATA_ROOT"
ln -sfn "$REPO_ROOT" "$PACKAGE_LINK"
echo "Linked $REPO_ROOT"
echo "    -> $PACKAGE_LINK"
echo "Lake root: $DATA_ROOT"

if [ ! -f "$PATCH" ]; then
  cat > "$PATCH" <<YAML
- insert:
    - id: scidatamas
      name: scidatamas-dsh-plugin
      config:
        root: $DATA_ROOT
YAML
  echo "Created $PATCH"
elif grep -qE '^[[:space:]]*-[[:space:]]*id:[[:space:]]*scidatamas[[:space:]]*$' "$PATCH"; then
  echo "Patch already contains a scidatamas row; leaving $PATCH unchanged."
  echo "Edit its config.root manually if the lake root changed."
else
  BACKUP="$PATCH.bak.$(date +%s)"
  cp "$PATCH" "$BACKUP"
  echo "Backup: $BACKUP"
  if grep -qE '^[[:space:]]*\[[[:space:]]*\][[:space:]]*$' "$PATCH"; then
    # A fresh DSH profile ships with an empty top-level array (`[]`).
    # Appending another top-level entry after it produces invalid YAML, so
    # replace that line in place and keep the surrounding comments.
    python3 - "$PATCH" "$DATA_ROOT" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
root = sys.argv[2]
lines = path.read_text().splitlines()
block = [
    "- insert:",
    "    - id: scidatamas",
    "      name: scidatamas-dsh-plugin",
    "      config:",
    f"        root: {root}",
]
out = []
replaced = False
for line in lines:
    if not replaced and line.strip() == "[]":
        out.extend(block)
        replaced = True
    else:
        out.append(line)
if not replaced:
    out.extend([""] + block)
path.write_text("\n".join(out) + "\n")
PY
  else
    cat >> "$PATCH" <<YAML

- insert:
    - id: scidatamas
      name: scidatamas-dsh-plugin
      config:
        root: $DATA_ROOT
YAML
  fi
  echo "Updated $PATCH"
fi

cat <<EOF

Next steps:
  1. Restart the DSH Web profile (or let dsh-hmr apply the patch).
  2. Ask the agent: show scidatamas_status
  3. Open the Data entry in the sidebar.

If the Web GUI is running from the npx cache, find the CLI with:
  find "\$HOME/.npm/_npx" -path '*/node_modules/.bin/dsh' -print

EOF
