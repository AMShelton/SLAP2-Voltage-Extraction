REPO="${REPO:-$HOME/SLAP2-Voltage-Extraction}"
URL="https://github.com/AllenNeuralDynamics/SLAP2-Voltage-Extraction.git"
BRANCH="python_translation"

if [[ ! -d "$REPO/.git" ]]; then
    git clone --branch "$BRANCH" --single-branch "$URL" "$REPO"
fi

git -C "$REPO" pull --ff-only origin "$BRANCH"
# cd() inside the batch command instead of relying on the shell's working
# directory, so the runner works even when pasted line-by-line.
matlab -batch "cd('$REPO'); fprintf('MATLAB: %s (%s) %s\n', version, version('-release'), computer('arch')); clear classes; setup; results = runtests('tests'); disp(table(results)); assertSuccess(results)"

MATLAB_STATUS=$?
echo "MATLAB finished with exit code $MATLAB_STATUS"
