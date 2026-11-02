classdef TestVoltage < matlab.unittest.TestCase
    %TESTVOLTAGE Public-entry tests using tiny synthetic HDF5 and DAT files.

    properties
        Root
        WorkDir
        OutputDir
    end

    methods (TestClassSetup)
        function addTestPaths(testCase)
            import matlab.unittest.fixtures.PathFixture

            testCase.Root = fileparts(fileparts(mfilename('fullpath')));
            testsDir = fullfile(testCase.Root, 'tests');
            testCase.applyFixture(PathFixture(testCase.Root));
            testCase.applyFixture(PathFixture( ...
                fullfile(testCase.Root, 'dependencies', 'io')));
            testCase.applyFixture(PathFixture( ...
                fullfile(testCase.Root, 'dependencies', 'gui')));
            testCase.applyFixture(PathFixture( ...
                fullfile(testCase.Root, 'source_extraction')));
            testCase.applyFixture(PathFixture( ...
                fullfile(testsDir, 'fakes')));
        end
    end

    methods (TestMethodSetup)
        function makeTemporaryFolders(testCase)
            import matlab.unittest.fixtures.TemporaryFolderFixture

            testCase.WorkDir = testCase.applyFixture(TemporaryFolderFixture).Folder;
            testCase.OutputDir = testCase.applyFixture(TemporaryFolderFixture).Folder;
        end
    end

    methods (Test)
        function testExtractsSingleRoiAndWritesPublicContract(testCase)
            trialTablePath = testCase.writeTrialTable('source.dat', 1, 8);
            testCase.writeRawFile('source.dat', int16(100:131));

            summary = Voltage(trialTablePath, testCase.params());

            expectedOutput = fullfile(testCase.OutputDir, 'result.h5');
            testCase.verifyEqual(summary.trialTablePath, trialTablePath);
            testCase.verifyEqual(summary.outputPath, expectedOutput);
            testCase.verifyEqual(summary.nPaths, 1);
            testCase.verifyEqual(summary.nTrials, 1);
            testCase.verifyEqual(summary.path(1).nAcquisitionROIs, 1);
            testCase.verifyEqual(summary.path(1).nROIs, 1);
            testCase.verifyEqual(summary.path(1).sourceRoiIdx, 1);
            testCase.verifyEqual(summary.path(1).sampleRateHz, 1000);
            testCase.verifyEqual(summary.path(1).totalSamples, 8);
            testCase.verifyEqual(summary.path(1).trialNumSamples, 8);
            testCase.verifyEqual(summary.path(1).trialEpoch, 1);
            testCase.verifyEqual(summary.path(1).inMemoryEpochIds, 1);
            testCase.verifyEmpty(summary.path(1).fallbackEpochIds);
            testCase.verifyTrue(isfile(expectedOutput));

            testCase.verifyEqual(char(h5read(expectedOutput, '/format_version')), '0.2.3');
            testCase.verifyEqual(h5read(expectedOutput, '/Path1/sample_rate_hz'), 1000);
            testCase.verifyEqual(double(h5read(expectedOutput, ...
                '/Path1/frame_info/trial_num_frames')), 8);
            testCase.verifyEqual(double(h5read(expectedOutput, ...
                '/Path1/frame_info/frame_line_idxs'))(:), (1:8)');
            testCase.verifyEqual(double(h5read(expectedOutput, ...
                '/Path1/frame_info/sample_epoch'))(:), ones(8, 1));
            testCase.verifyEqual(double(h5read(expectedOutput, ...
                '/Path1/sources/spatial/source_roi_index')), 1);
            testCase.verifyEqual(double(h5read(expectedOutput, ...
                '/Path1/sources/spatial/roi_pixel_count')), 1);

            raw = h5read(expectedOutput, '/Path1/sources/temporal/raw_f');
            f0 = h5read(expectedOutput, '/Path1/sources/temporal/f0');
            dff = h5read(expectedOutput, '/Path1/sources/temporal/dff');
            testCase.verifyClass(raw, 'single');
            testCase.verifySize(raw, [1 1 8]);
            testCase.verifySize(f0, [1 1 8]);
            testCase.verifySize(dff, [1 1 8]);
            testCase.verifyTrue(all(isfinite(raw(:))));
            testCase.verifyGreaterThan(min(raw(:)), single(0));
            testCase.verifyEqual(f0, repmat(median(raw(:)), size(f0)), ...
                'AbsTol', single(1e-5));
            testCase.verifyEqual(dff, (raw - f0) ./ f0, ...
                'AbsTol', single(1e-5));
            testCase.verifyEqual(h5readatt(expectedOutput, ...
                '/Path1/sources/temporal/dff', 'indicator_direction'), 'increases');
            testCase.verifyEqual(h5readatt(expectedOutput, ...
                '/Path1/sources/temporal/dff', 'sign_convention'), ...
                'Positive dff corresponds to positive membrane-voltage deflection.');
        end

        function testDirectoryInputResolvesTrialTable(testCase)
            testCase.writeTrialTable('source.dat', 1, 4);
            testCase.writeRawFile('source.dat', int16(20:35));

            summary = Voltage(testCase.WorkDir, testCase.params());

            testCase.verifyEqual(summary.trialTablePath, ...
                fullfile(testCase.WorkDir, 'trial_table.h5'));
        end

        function testExistingOutputIsPreservedWithoutOverwrite(testCase)
            trialTablePath = testCase.writeTrialTable('source.dat', 1, 4);
            outputPath = fullfile(testCase.OutputDir, 'result.h5');
            testCase.writeTextFile(outputPath, 'sentinel');

            testCase.verifyError(@() Voltage(trialTablePath, testCase.params()), ...
                'Voltage:OutputExists');
            testCase.verifyEqual(fileread(outputPath), 'sentinel');
        end

        function testShapeMismatchCleansPartialOutput(testCase)
            trialTablePath = testCase.writeTrialTable( ...
                {'source.dat', 'source.dat'}, [1 5], 8);
            outputPath = fullfile(testCase.OutputDir, 'result.h5');

            testCase.verifyError(@() Voltage(trialTablePath, testCase.params()), ...
                'Voltage:TrialTableShapeMismatch');
            testCase.verifyFalse(isfile(outputPath));
        end

        function testNoVoltageRoisFailsWithoutLeavingOutput(testCase)
            trialTablePath = testCase.writeTrialTable('no_voltage.dat', 1, 4);
            testCase.writeRawFile('no_voltage.dat', int16(1:16));
            outputPath = fullfile(testCase.OutputDir, 'result.h5');

            testCase.verifyError(@() Voltage(trialTablePath, testCase.params()), ...
                'Voltage:NoVoltageROIs');
            testCase.verifyFalse(isfile(outputPath));
        end

        function testMissingTrialTableReportsPublicError(testCase)
            testCase.verifyError(@() Voltage(fullfile(testCase.WorkDir, 'missing.h5'), ...
                testCase.params()), 'Voltage:TrialTableNotFound');
        end
    end

    methods (Access = private)
        function params = params(testCase)
            params = struct( ...
                'outputDir', testCase.OutputDir, ...
                'outputFilename', 'result.h5', ...
                'overwrite', false, ...
                'useParallel', false, ...
                'precision', 'single', ...
                'indicatorName', 'test', ...
                'indicatorDirection', 'increases', ...
                'f0Method', 'static', ...
                'f0Percentile', 50, ...
                'h5ChunkSamples', 16, ...
                'h5Deflate', 0);
        end

        function path = writeTrialTable(testCase, filename, firstLine, lastLine)
            table = struct();
            table.datadr = testCase.WorkDir;
            if iscell(filename)
                table.filename = filename;
            else
                table.filename = {filename};
            end
            table.epoch = 1;
            table.slap2_info = struct( ...
                'first_line', firstLine, ...
                'last_line', lastLine, ...
                'line_range_convention', 'inclusive');
            path = fullfile(testCase.WorkDir, 'trial_table.h5');
            saveStructToH5(table, path);
        end

        function writeRawFile(testCase, name, values)
            path = fullfile(testCase.WorkDir, name);
            fid = fopen(path, 'w');
            testCase.assertGreaterThanOrEqual(fid, 0);
            cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
            fwrite(fid, values, 'int16');
        end

        function writeTextFile(testCase, path, text)
            fid = fopen(path, 'w');
            testCase.assertGreaterThanOrEqual(fid, 0);
            cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
            fprintf(fid, '%s', text);
        end
    end
end
