#!/usr/bin/env bash
set -euo pipefail

BRANCH="python_translation"
REPO_URL="https://github.com/AllenNeuralDynamics/SLAP2-Voltage-Extraction.git"
REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

trap 'status=$?; echo "Test runner failed on line $LINENO (exit $status)." >&2; exit $status' ERR

cd "$REPO_DIR"
if [[ ! -d .git ]]; then
	echo "Not a Git checkout: $REPO_DIR" >&2
	echo "Clone $REPO_URL, then run this script from that checkout." >&2
	exit 2
fi

if git remote get-url origin >/dev/null 2>&1; then
	git remote set-url origin "$REPO_URL"
else
	git remote add origin "$REPO_URL"
fi

git fetch origin "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
	git switch "$BRANCH"
else
	git switch --create "$BRANCH" --track "origin/$BRANCH"
fi
git merge --ff-only "origin/$BRANCH"
matlab -batch "clear classes; setup; results = runtests('tests'); disp(table(results)); assertSuccess(results)"
