#!/usr/bin/env bash

REPO_URL="https://github.com/AllenNeuralDynamics/SLAP2-Voltage-Extraction.git"
BRANCH="python_translation"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if REPO_DIR="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)"; then
    echo "Using repository containing this script: $REPO_DIR"
else
    REPO_DIR="$HOME/SLAP2-Voltage-Extraction"
    if [[ -d "$REPO_DIR/.git" ]]; then
        echo "Using existing repository: $REPO_DIR"
    elif [[ -e "$REPO_DIR" ]]; then
        echo "Cannot clone: $REPO_DIR exists but is not a Git repository." >&2
        return 2 2>/dev/null || exit 2
    else
        git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$REPO_DIR" || \
            { status=$?; return "$status" 2>/dev/null || exit "$status"; }
    fi
fi

if ! git -C "$REPO_DIR" remote get-url origin >/dev/null 2>&1; then
    git -C "$REPO_DIR" remote add origin "$REPO_URL"
fi

git -C "$REPO_DIR" fetch origin "$BRANCH" &&
git -C "$REPO_DIR" switch "$BRANCH" &&
git -C "$REPO_DIR" reset --hard "origin/$BRANCH" || \
    { status=$?; return "$status" 2>/dev/null || exit "$status"; }

cd "$REPO_DIR" || { status=$?; return "$status" 2>/dev/null || exit "$status"; }
matlab -batch "fprintf('MATLAB version: %s\n', version); fprintf('MATLAB release: %s\n', version('-release')); fprintf('Architecture: %s\n', computer('arch')); disp('Installed products:'); ver; clear classes; setup; results = runtests('tests'); disp(table(results)); assertSuccess(results)"

MATLAB_STATUS=$?
echo "MATLAB finished with exit code $MATLAB_STATUS"
