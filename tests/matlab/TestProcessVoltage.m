classdef TestProcessVoltage < matlab.unittest.TestCase
    %TESTPROCESSVOLTAGE Unit tests for validation and trial-table decisions.

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
            testCase.applyFixture(PathFixture(fullfile(testsDir,'fakes')));
            testCase.applyFixture(PathFixture( ...
                fullfile(testsDir,'process_voltage_fakes')));
        end
    end

    methods (TestMethodSetup)
        function configureTest(testCase)
            import matlab.unittest.fixtures.TemporaryFolderFixture

            testCase.TempDir = testCase.applyFixture( ...
                TemporaryFolderFixture).Folder;
            global PROCESS_VOLTAGE_BUILD_DOUBLE
            PROCESS_VOLTAGE_BUILD_DOUBLE = struct('mode','empty','calls',{{}});
        end
    end

    methods (TestMethodTeardown)
        function clearDouble(~)
            clear global PROCESS_VOLTAGE_BUILD_DOUBLE
        end
    end

    methods (Test)
        function testRejectsMissingDataDirectory(testCase)
            missing = fullfile(testCase.TempDir,'missing');

            testCase.verifyError(@() processVoltage( ...
                missing,testCase.TempDir,false,struct(),false), ...
                'processVoltage:InvalidDataDirectory');
        end

        function testRejectsNonlogicalUseAllFiles(testCase)
            testCase.verifyError(@() processVoltage( ...
                testCase.TempDir,testCase.TempDir,2,struct(),false), ...
                'setParams:InvalidLogical');
        end

        function testRejectsNonlogicalShowParamsGUI(testCase)
            testCase.verifyError(@() processVoltage( ...
                testCase.TempDir,testCase.TempDir,false,struct(),'yes'), ...
                'setParams:InvalidLogical');
        end

        function testEmptyBuilderResultUsesRequestedPolicy(testCase)
            global PROCESS_VOLTAGE_BUILD_DOUBLE
            PROCESS_VOLTAGE_BUILD_DOUBLE.mode = 'empty';

            testCase.verifyError(@() processVoltage( ...
                testCase.TempDir,testCase.TempDir,true,struct(),false), ...
                'processVoltage:EmptyTrialTable');
            testCase.verifyNumElements(PROCESS_VOLTAGE_BUILD_DOUBLE.calls,1);
            call = PROCESS_VOLTAGE_BUILD_DOUBLE.calls{1};
            testCase.verifyEqual(call.dr,testCase.TempDir);
            testCase.verifyEqual(call.savedr,testCase.TempDir);
            testCase.verifyTrue(call.useAllFiles);
        end

        function testBuilderMustCreateTrialTableFile(testCase)
            global PROCESS_VOLTAGE_BUILD_DOUBLE
            PROCESS_VOLTAGE_BUILD_DOUBLE.mode = 'missing-file';

            testCase.verifyError(@() processVoltage( ...
                testCase.TempDir,testCase.TempDir,false,struct(),false), ...
                'processVoltage:MissingTrialTable');
        end

        function testIncompleteTrialTableIsRejected(testCase)
            global PROCESS_VOLTAGE_BUILD_DOUBLE
            PROCESS_VOLTAGE_BUILD_DOUBLE.mode = 'incomplete';

            testCase.verifyError(@() processVoltage( ...
                testCase.TempDir,testCase.TempDir,false,struct(),false), ...
                'processVoltage:IncompleteTrialTable');
        end

        function testUnknownVoltageParameterIsRejectedBeforeExtraction(testCase)
            global PROCESS_VOLTAGE_BUILD_DOUBLE
            PROCESS_VOLTAGE_BUILD_DOUBLE.mode = 'valid';

            testCase.verifyError(@() processVoltage( ...
                testCase.TempDir,testCase.TempDir,false, ...
                struct('notAVoltageParameter',1),false), ...
                'processVoltage:UnknownParameter');
        end

        function testExistingOutputStopsBeforeExtraction(testCase)
            global PROCESS_VOLTAGE_BUILD_DOUBLE
            PROCESS_VOLTAGE_BUILD_DOUBLE.mode = 'valid';
            outputDir = fullfile(testCase.TempDir,'custom-output');
            mkdir(outputDir);
            outputPath = fullfile(outputDir,'already-there.h5');
            fid = fopen(outputPath,'w');
            testCase.assertGreaterThanOrEqual(fid,0);
            fclose(fid);
            params = struct( ...
                'outputDir',outputDir, ...
                'outputFilename','already-there.h5', ...
                'overwrite',false);

            testCase.verifyError(@() processVoltage( ...
                testCase.TempDir,testCase.TempDir,false,params,false), ...
                'processVoltage:OutputExists');
        end
    end
end
