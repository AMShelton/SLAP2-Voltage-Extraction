#!/usr/bin/env bash
set -euo pipefail

BRANCH="python_translation"
cd "$(git rev-parse --show-toplevel)"
git fetch origin "$BRANCH"
git switch "$BRANCH"
git pull --ff-only origin "$BRANCH"
matlab -batch "clear classes; setup; results = runtests('tests'); disp(table(results)); assertSuccess(results)"
