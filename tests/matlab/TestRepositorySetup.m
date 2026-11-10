classdef TestRepositorySetup < matlab.unittest.TestCase
    %TESTREPOSITORYSETUP Runtime tests for setup path and dependency behavior.

    properties
        Root
        FakeRoot
    end

    methods (TestClassSetup)
        function locateRepository(testCase)
            testCase.Root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
            testCase.FakeRoot = fullfile(testCase.Root, 'tests', 'matlab', 'fakes');
        end
    end

    methods (Test)
        function testSetupAddsRepositoryRootsAndResolvesDependencies(testCase)
            import matlab.unittest.fixtures.PathFixture

            expectedPaths = testCase.expectedPaths();
            originalPath = path;
            cleanup = onCleanup(@() path(originalPath)); %#ok<NASGU>
            % Keep the repository root present so the actual setup function is
            % callable; remove only the roots setup itself is responsible for.
            for k = 2:numel(expectedPaths)
                if testCase.pathContains(expectedPaths{k})
                    rmpath(expectedPaths{k});
                end
            end
            testCase.applyFixture(PathFixture(testCase.FakeRoot));

            output = evalc('setup();');

            for k = 1:numel(expectedPaths)
                testCase.verifyTrue(testCase.pathContains(expectedPaths{k}), ...
                    sprintf('setup did not add %s.', expectedPaths{k}));
            end
            testCase.verifyNotEmpty(which('slap2.util.MultiDataFiles'));
            testCase.verifyNotEmpty(which('slap2.util.datafile.trace.Trace'));
            testCase.verifyNotEmpty(which('slap2.util.datafile.trace.TracePixel'));
            testCase.verifySubstring(output, 'SLAP2 Voltage Extraction paths configured.');
        end

        function testSetupIsIdempotent(testCase)
            import matlab.unittest.fixtures.PathFixture

            originalPath = path;
            cleanup = onCleanup(@() path(originalPath)); %#ok<NASGU>
            testCase.applyFixture(PathFixture(testCase.FakeRoot));

            evalc('setup();');
            evalc('setup();');

            for expected = testCase.expectedPaths()
                testCase.verifyEqual(testCase.pathEntryCount(expected{1}), 1, ...
                    sprintf('Repeated setup duplicated %s.', expected{1}));
            end
        end

    end

    methods (Access = private)
        function paths = expectedPaths(testCase)
            paths = { ...
                testCase.Root, ...
                fullfile(testCase.Root, 'source_extraction'), ...
                fullfile(testCase.Root, 'dependencies', 'io'), ...
                fullfile(testCase.Root, 'dependencies', 'gui'), ...
                fullfile(testCase.Root, 'dependencies', 'slap2_trace'), ...
                fullfile(testCase.Root, 'presets')};
        end

        function tf = pathContains(~, target)
            entries = strsplit(path, pathsep);
            tf = any(strcmpi(entries, target));
        end

        function count = pathEntryCount(~, target)
            entries = strsplit(path, pathsep);
            count = nnz(strcmpi(entries, target));
        end

    end
end
