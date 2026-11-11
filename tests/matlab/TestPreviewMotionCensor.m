classdef TestPreviewMotionCensor < matlab.unittest.TestCase
    %TESTPREVIEWMOTIONCENSOR Unit tests for the non-GUI preview wrapper.

    properties
        Root
        TempDir
    end

    methods (TestClassSetup)
        function addRepositoryPaths(testCase)
            import matlab.unittest.fixtures.PathFixture

            testCase.Root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
            testsDir = fullfile(testCase.Root,'tests','matlab');
            testCase.applyFixture(PathFixture(testCase.Root));
            testCase.applyFixture(PathFixture( ...
                fullfile(testCase.Root,'source_extraction_matlab')));
            testCase.applyFixture(PathFixture( ...
                fullfile(testCase.Root,'dependencies','slap2_motion')));
            testCase.applyFixture(PathFixture(fullfile(testsDir,'fakes')));
        end
    end

    methods (TestMethodSetup)
        function makeTemporaryFolder(testCase)
            import matlab.unittest.fixtures.TemporaryFolderFixture

            testCase.TempDir = testCase.applyFixture( ...
                TemporaryFolderFixture).Folder;
            oldVisibility = get(groot,'DefaultFigureVisible');
            set(groot,'DefaultFigureVisible','off');
            testCase.addTeardown(@() set(groot, ...
                'DefaultFigureVisible',oldVisibility));
            testCase.addTeardown(@() close(findall(groot,'Type','figure')));
        end
    end

    methods (Test)
        function testHeadlessStationaryPreviewReturnsScientificResult(testCase)
            filename = testCase.touch('stationary.dat');

            [params,info] = previewMotionCensor(filename,struct(),false);

            testCase.verifyTrue(params.motionCensorEnable);
            testCase.verifyFalse(any(info.mask));
            testCase.verifyEqual(info.fractionCensored,0);
            testCase.verifyEqual(info.motion.x,zeros(2,1));
            testCase.verifyEqual(info.motion.y,zeros(2,1));
            testCase.verifyEqual(info.motion.z,[0;8]);
            testCase.verifyEqual(info.motion.lineIds,[1;9]);
            testCase.verifyEqual(info.motion.numCycles,2);
            testCase.verifyEqual(info.motion.linesPerCycle,8);
            testCase.verifyEqual(info.motion.fsOffsets,125);
        end

        function testHeadlessPreviewMergesKnownOverridesOnly(testCase)
            filename = testCase.touch('overrides.dat');
            input = struct( ...
                'motionPixelSize_um',0.5, ...
                'motionSamplesPerCycle',2, ...
                'unknownField',123);

            [params,info] = previewMotionCensor(filename,input,false);

            testCase.verifyEqual(params.motionPixelSize_um,0.5);
            testCase.verifyEqual(params.motionSamplesPerCycle,2);
            testCase.verifyFalse(isfield(params,'unknownField'));
            testCase.verifyEqual(info.motion.lineIds,[1;5;9;13]);
            testCase.verifyEqual(info.motion.fsOffsets,250);
            testCase.verifyFalse(any(info.mask));
        end

        function testInvalidMotionOverrideIsRejected(testCase)
            filename = testCase.touch('invalid.dat');

            caught = false;
            try
                previewMotionCensor(filename, ...
                    struct('motionSamplesPerCycle',0),false);
            catch exception
                caught = true;
                testCase.verifySubstring(exception.identifier,'expectedPositive');
            end
            testCase.verifyTrue(caught, ...
                'A nonpositive motionSamplesPerCycle should fail validation.');
        end
    end

    methods (Access = private)
        function filename = touch(testCase,name)
            filename = fullfile(testCase.TempDir,name);
            fid = fopen(filename,'w');
            testCase.assertGreaterThanOrEqual(fid,0);
            fclose(fid);
        end
    end
end
