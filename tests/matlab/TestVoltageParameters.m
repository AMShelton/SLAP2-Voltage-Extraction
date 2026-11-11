classdef TestVoltageParameters < matlab.unittest.TestCase
    %TESTVOLTAGEPARAMETERS Characterization tests for setParams and presets.

    properties
        TemporaryFolder
    end

    methods (TestClassSetup)
        function addProductionPaths(testCase)
            import matlab.unittest.fixtures.PathFixture

            testsDir = fileparts(mfilename('fullpath'));
            repoRoot = fileparts(fileparts(testsDir));
            testCase.applyFixture(PathFixture(repoRoot));
            testCase.applyFixture(PathFixture(fullfile(repoRoot, 'dependencies', 'gui')));
            testCase.applyFixture(PathFixture(fullfile(repoRoot, 'source_extraction_matlab')));
            testCase.applyFixture(PathFixture(fullfile(repoRoot, 'presets')));
        end
    end

    methods (TestMethodSetup)
        function makeTemporaryFolder(testCase)
            import matlab.unittest.fixtures.TemporaryFolderFixture

            testCase.TemporaryFolder = ...
                testCase.applyFixture(TemporaryFolderFixture).Folder;
        end
    end

    methods (Test)
        function testVoltageDefaults(testCase)
            params = setParams('Voltage', struct());

            expected = struct( ...
                'chIdx', 1, ...
                'zIdx', 1, ...
                'traceWindow_lines', 16, ...
                'traceExpectedWindow_lines', 5000, ...
                'indicatorName', '', ...
                'indicatorDirection', 'auto', ...
                'f0Method', 'robust', ...
                'f0Percentile', 50, ...
                'f0Bin_s', 5, ...
                'f0Smooth_s', 180, ...
                'useParallel', true, ...
                'nWorkers', 4, ...
                'maxConcurrentROIs', 2, ...
                'precision', 'single', ...
                'outputDir', '', ...
                'outputFilename', 'VoltageSummary.h5', ...
                'overwrite', false, ...
                'h5ChunkSamples', 100000, ...
                'h5Deflate', 0, ...
                'motionCensorEnable', false, ...
                'motionPixelSize_um', 0.25, ...
                'motionMedianWindow_s', 4, ...
                'motionThresh', 2.5, ...
                'motionScaleFloor_um', 0.25, ...
                'motionAbsMax_um', 0, ...
                'motionPad_s', 0.025, ...
                'motionMergeGap_s', 0.05, ...
                'motionDiscardInitial_s', 0, ...
                'motionSamplesPerCycle', 1, ...
                'motionMaxFracCensored', 0.25);
            testCase.verifyEqual(params, expected);
        end

        function testStructOverridesAreMergedAndUnknownFieldsSurvive(testCase)
            overrides = struct( ...
                'chIdx', 2, ...
                'indicatorName', "ASAP8", ...
                'indicatorDirection', 'increases', ...
                'f0Method', 'static', ...
                'precision', 'double', ...
                'outputDir', "custom", ...
                'outputFilename', "result.h5", ...
                'customMetadata', 17);

            params = setParams('Voltage', overrides);

            testCase.verifyEqual(params.chIdx, 2);
            testCase.verifyEqual(params.indicatorName, 'ASAP8');
            testCase.verifyEqual(params.indicatorDirection, 'increases');
            testCase.verifyEqual(params.f0Method, 'static');
            testCase.verifyEqual(params.precision, 'double');
            testCase.verifyEqual(params.outputDir, 'custom');
            testCase.verifyEqual(params.outputFilename, 'result.h5');
            testCase.verifyEqual(params.customMetadata, 17);
            testCase.verifyEqual(params.traceWindow_lines, 16);
        end

        function testCountAndCompressionValuesAreRounded(testCase)
            params = setParams('Voltage', struct( ...
                'nWorkers', 2.6, ...
                'maxConcurrentROIs', 1.5, ...
                'h5ChunkSamples', 10.6, ...
                'h5Deflate', 2.6));

            testCase.verifyEqual(params.nWorkers, 3);
            testCase.verifyEqual(params.maxConcurrentROIs, 2);
            testCase.verifyEqual(params.h5ChunkSamples, 11);
            testCase.verifyEqual(params.h5Deflate, 3);
            testCase.verifyClass(params.nWorkers, 'double');
        end

        function testLogicalFlagsAcceptLogicalAndNumericBinaryValues(testCase)
            params = setParams('Voltage', struct( ...
                'useParallel', 0, 'overwrite', 1));
            testCase.verifyEqual(params.useParallel, false);
            testCase.verifyEqual(params.overwrite, true);
            testCase.verifyClass(params.useParallel, 'logical');
            testCase.verifyClass(params.overwrite, 'logical');

            params = setParams('Voltage', struct( ...
                'useParallel', true, 'overwrite', false));
            testCase.verifyTrue(params.useParallel);
            testCase.verifyFalse(params.overwrite);
        end

        function testJsonTextInput(testCase)
            json = ['{"indicatorName":"ASAP7y","indicatorDirection":"decreases",' ...
                '"nWorkers":3.7,"useParallel":false}'];

            params = setParams('Voltage', json);

            testCase.verifyEqual(params.indicatorName, 'ASAP7y');
            testCase.verifyEqual(params.indicatorDirection, 'decreases');
            testCase.verifyEqual(params.nWorkers, 4);
            testCase.verifyFalse(params.useParallel);
        end

        function testJsonFileInput(testCase)
            filename = fullfile(testCase.TemporaryFolder, 'params.json');
            testCase.writeText(filename, ...
                '{"f0Method":"static","f0Percentile":25,"precision":"double"}');

            params = setParams('Voltage', filename);

            testCase.verifyEqual(params.f0Method, 'static');
            testCase.verifyEqual(params.f0Percentile, 25);
            testCase.verifyEqual(params.precision, 'double');
        end

        function testMatFileOptsOutInput(testCase)
            filename = fullfile(testCase.TemporaryFolder, 'optsOut.mat');
            optsOut = struct('indicatorName', 'ASAP8', ...
                'indicatorDirection', 'increases'); %#ok<NASGU>
            save(filename, 'optsOut');

            params = setParams('Voltage', filename);

            testCase.verifyEqual(params.indicatorName, 'ASAP8');
            testCase.verifyEqual(params.indicatorDirection, 'increases');
        end

        function testMatFileParamsInput(testCase)
            filename = fullfile(testCase.TemporaryFolder, 'params.mat');
            params = struct('f0Bin_s', 2, 'f0Smooth_s', 7); %#ok<NASGU>
            save(filename, 'params');

            loaded = setParams('Voltage', filename);

            testCase.verifyEqual(loaded.f0Bin_s, 2);
            testCase.verifyEqual(loaded.f0Smooth_s, 7);
        end

        function testMatFileSingleStructVariableInput(testCase)
            filename = fullfile(testCase.TemporaryFolder, 'preset.mat');
            customPreset = struct('h5ChunkSamples', 12.7); %#ok<NASGU>
            save(filename, 'customPreset');

            params = setParams('Voltage', filename);

            testCase.verifyEqual(params.h5ChunkSamples, 13);
        end

        function testASAP7PresetAndOverrides(testCase)
            params = ASAP7_params();
            testCase.verifyEqual(params.indicatorName, 'ASAP7');
            testCase.verifyEqual(params.indicatorDirection, 'decreases');
            testCase.verifyEqual(params.f0Method, 'robust');

            overridden = ASAP7_params(struct( ...
                'indicatorName', 'ASAP7b', ...
                'precision', 'double', ...
                'f0Percentile', 20));
            testCase.verifyEqual(overridden.indicatorName, 'ASAP7b');
            testCase.verifyEqual(overridden.indicatorDirection, 'decreases');
            testCase.verifyEqual(overridden.precision, 'double');
            testCase.verifyEqual(overridden.f0Percentile, 20);
        end

        function testASAP8PresetAndOverrides(testCase)
            params = ASAP8_params();
            testCase.verifyEqual(params.indicatorName, 'ASAP8');
            testCase.verifyEqual(params.indicatorDirection, 'increases');

            overridden = ASAP8_params(struct( ...
                'indicatorDirection', 'decreases', ...
                'outputFilename', 'custom.h5'));
            testCase.verifyEqual(overridden.indicatorName, 'ASAP8');
            testCase.verifyEqual(overridden.indicatorDirection, 'decreases');
            testCase.verifyEqual(overridden.outputFilename, 'custom.h5');
        end

        function testUnknownFunctionError(testCase)
            testCase.verifyError(@() setParams('NotVoltage', struct()), ...
                'setParams:UnknownFunction');
        end

        function testInvalidInputTypeError(testCase)
            testCase.verifyError(@() setParams('Voltage', {struct()}), ...
                'setParams:InvalidInput');
        end

        function testInvalidMatPresetError(testCase)
            filename = fullfile(testCase.TemporaryFolder, 'invalid.mat');
            first = struct('f0Method', 'static'); %#ok<NASGU>
            second = 2; %#ok<NASGU>
            save(filename, 'first', 'second');

            testCase.verifyError(@() setParams('Voltage', filename), ...
                'setParams:InvalidPreset');
        end

        function testInvalidLogicalValuesError(testCase)
            invalidValues = {-1, 0.5, 2, [0 1], NaN, 'true'};
            for idx = 1:numel(invalidValues)
                value = invalidValues{idx};
                testCase.verifyError(@() setParams('Voltage', ...
                    struct('useParallel', value)), ...
                    'setParams:InvalidLogical');
            end
        end

        function testInvalidOutputFilenameError(testCase)
            invalidNames = {'', '   ', ""};
            for idx = 1:numel(invalidNames)
                name = invalidNames{idx};
                testCase.verifyError(@() setParams('Voltage', ...
                    struct('outputFilename', name)), ...
                    'setParams:InvalidOutputFilename');
            end
        end

        function testInvalidChoiceValuesFailValidation(testCase)
            invalidOverrides = { ...
                struct('indicatorDirection', 'sideways'), ...
                struct('f0Method', 'mean'), ...
                struct('precision', 'half')};
            for idx = 1:numel(invalidOverrides)
                testCase.verifyError(@() setParams('Voltage', ...
                    invalidOverrides{idx}), ?MException);
            end
        end

        function testInvalidNumericValuesFailValidation(testCase)
            invalidOverrides = { ...
                struct('chIdx', 0), ...
                struct('zIdx', 1.5), ...
                struct('traceWindow_lines', Inf), ...
                struct('traceExpectedWindow_lines', -1), ...
                struct('f0Percentile', -1), ...
                struct('f0Percentile', 101), ...
                struct('f0Bin_s', 0), ...
                struct('f0Smooth_s', NaN), ...
                struct('nWorkers', 0), ...
                struct('maxConcurrentROIs', Inf), ...
                struct('h5ChunkSamples', 0), ...
                struct('h5Deflate', -1), ...
                struct('h5Deflate', 10)};
            for idx = 1:numel(invalidOverrides)
                testCase.verifyError(@() setParams('Voltage', ...
                    invalidOverrides{idx}), ?MException);
            end
        end
    end

    methods (Access = private)
        function writeText(~, filename, contents)
            fid = fopen(filename, 'w');
            assert(fid >= 0, 'Could not create test fixture: %s', filename);
            cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
            fprintf(fid, '%s', contents);
        end
    end
end