#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="/home/ForgenHide/Forge-and-Hide"
BRANCH="main"
WSGI_FILE="${1:-}"

fail() {
    printf 'Deploy stopped: %s\n' "$*" >&2
    exit 1
}

[[ "$WSGI_FILE" = /* && -f "$WSGI_FILE" && -w "$WSGI_FILE" ]] \
    || fail "Pass the writable WSGI file path shown in PythonAnywhere's Web tab."
[[ -n "${VIRTUAL_ENV:-}" && -x "$VIRTUAL_ENV/bin/python" ]] \
    || fail "Activate the forge-env virtualenv before running this task."
command -v flock >/dev/null 2>&1 || fail "The flock command is required."

exec 9>"$HOME/.forge-and-hide-deploy.lock"
flock -n 9 || exit 0

cd "$PROJECT_DIR" || fail "Project directory not found: $PROJECT_DIR"
[[ "$(git branch --show-current)" = "$BRANCH" ]] \
    || fail "Expected branch $BRANCH."
[[ -z "$(git status --porcelain)" ]] \
    || fail "Working tree has changes; refusing to overwrite them."

GIT_TERMINAL_PROMPT=0 git fetch origin "$BRANCH"
target_commit="$(git rev-parse --verify "origin/$BRANCH^{commit}")"
current_commit="$(git rev-parse --verify HEAD)"
state_file="$HOME/.forge-and-hide-deployed-commit"
deployed_commit=""
if [[ -r "$state_file" ]]; then
    deployed_commit="$(<"$state_file")"
fi
if [[ -z "$deployed_commit" ]] \
    || ! git cat-file -e "$deployed_commit^{commit}" 2>/dev/null; then
    deployed_commit="$current_commit"
    has_deployed_state=0
else
    has_deployed_state=1
fi

if [[ "$current_commit" != "$target_commit" ]]; then
    git merge-base --is-ancestor "$current_commit" "$target_commit" \
        || fail "Remote branch is not a fast-forward; resolve the branch manually."
fi

if [[ "$has_deployed_state" -eq 1 && "$target_commit" = "$deployed_commit" ]]; then
    printf 'Already deployed: %s\n' "$target_commit"
    exit 0
fi

requirements_changed=0
git diff --quiet "$deployed_commit" "$target_commit" -- requirements.txt \
    || requirements_changed=1
catalog_changed=0
if [[ "$has_deployed_state" -eq 0 ]]; then
    if [[ -f deployment/catalog.json ]]; then
        catalog_changed=1
    fi
else
    git diff --quiet "$deployed_commit" "$target_commit" -- \
        deployment/catalog.json deployment/uploads || catalog_changed=1
fi

if [[ "$current_commit" != "$target_commit" ]]; then
    git merge --ff-only "$target_commit"
fi

if [[ "$requirements_changed" -eq 1 ]]; then
    "$VIRTUAL_ENV/bin/python" -m pip install -r requirements.txt
fi

"$VIRTUAL_ENV/bin/python" -m flask --app app db upgrade
if [[ "$catalog_changed" -eq 1 ]]; then
    "$VIRTUAL_ENV/bin/python" scripts/import_deploy_catalog.py \
        --snapshot deployment/catalog.json \
        --assets deployment/uploads \
        --database instance/forge_and_hide.db \
        --apply
fi
touch "$WSGI_FILE"

state_tmp="${state_file}.tmp"
printf '%s\n' "$target_commit" > "$state_tmp"
mv "$state_tmp" "$state_file"
printf 'Deployed %s and reloaded the web app.\n' "$target_commit"
