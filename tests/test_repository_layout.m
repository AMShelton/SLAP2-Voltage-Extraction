function tests = test_repository_layout
tests = functiontests(localfunctions);
end

function testCoreEntryPointsExist(testCase)
repoRoot = fileparts(fileparts(mfilename('fullpath')));
verifyEqual(testCase, exist(fullfile(repoRoot, 'buildTrialTableSLAP2.m'), 'file'), 2);
verifyEqual(testCase, exist(fullfile(repoRoot, 'source_extraction', 'extractDendrites.m'), 'file'), 2);
end

function testSourceFilesParse(testCase)
repoRoot = fileparts(fileparts(mfilename('fullpath')));
files = {
    fullfile(repoRoot, 'buildTrialTableSLAP2.m')
    fullfile(repoRoot, 'source_extraction', 'extractDendrites.m')
    };
for i = 1:numel(files)
    msgs = checkcode(files{i}, '-id');
    ids = {msgs.id};
    parseLike = cellfun(@(x) ~isempty(regexpi(x, 'parse|syntax', 'once')), ids);
    verifyFalse(testCase, any(parseLike), sprintf('Parser-like MATLAB diagnostics in %s', files{i}));
end
end
