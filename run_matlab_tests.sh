REPO="$HOME/SLAP2-Voltage-Extraction"
URL="https://github.com/AllenNeuralDynamics/SLAP2-Voltage-Extraction.git"
BRANCH="python_translation"

if [[ ! -d "$REPO/.git" ]]; then
    git clone --branch "$BRANCH" --single-branch "$URL" "$REPO"
fi

git -C "$REPO" pull --ff-only origin "$BRANCH"
cd "$REPO"
matlab -batch "fprintf('MATLAB: %s (%s) %s\n', version, version('-release'), computer('arch')); clear classes; setup; results = runtests('tests'); disp(table(results)); assertSuccess(results)"

MATLAB_STATUS=$?
echo "MATLAB finished with exit code $MATLAB_STATUS"
