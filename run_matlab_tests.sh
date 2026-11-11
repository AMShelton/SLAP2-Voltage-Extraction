REPO="${REPO:-$HOME/SLAP2-Voltage-Extraction}"
URL="https://github.com/AllenNeuralDynamics/SLAP2-Voltage-Extraction.git"
BRANCH="python_translation"

if [[ ! -d "$REPO/.git" ]]; then
    git clone --branch "$BRANCH" --single-branch "$URL" "$REPO"
fi

git -C "$REPO" pull --ff-only origin "$BRANCH"

MATLAB_COMMAND="cd('$REPO'); fprintf('MATLAB: %s (%s) %s\\n', version, version('-release'), computer('arch')); clear classes; setup; suite = testsuite(fullfile('$REPO', 'tests', 'matlab'), 'IncludeSubfolders', true); assert(~isempty(suite), 'SLAP2VoltageExtraction:NoTestsDiscovered', 'No MATLAB tests were discovered.'); results = run(suite); disp(table(results)); assertSuccess(results);"

matlab -batch "$MATLAB_COMMAND"

MATLAB_STATUS=$?
echo "MATLAB finished with exit code $MATLAB_STATUS"
exit "$MATLAB_STATUS"
