classdef TestBuildTrialTableSLAP2 < matlab.unittest.TestCase
    %TESTBUILDTRIALTABLESLAP2 Unit tests for buildTrialTableSLAP2.
    %
    % These tests use small text files and test doubles under tests/fakes.
    % No real SLAP2 DAT data, reference TIFF data, or external SLAP2 reader
    % installation is required.

    properties
        DataRoot
        DataDir
        SaveDir
        LinePeriod_s = 1e-4
        StartTime = datetime(2024, 2, 1, 12, 0, 0, 'TimeZone', 'local')
    end

    methods (TestClassSetup)
        function addRepositoryPaths(testCase)
            import matlab.unittest.fixtures.PathFixture

            testsDir = fileparts(mfilename('fullpath'));
            repoRoot = fileparts(testsDir);
            testCase.applyFixture(PathFixture(repoRoot));
            testCase.applyFixture(PathFixture( ...
                fullfile(repoRoot, 'dependencies'), 'IncludingSubfolders', true));

            % Add this last so the test doubles shadow external readers.
            testCase.applyFixture(PathFixture(fullfile(testsDir, 'fakes')));
        end
    end

    methods (TestMethodSetup)
        function makeTemporaryFolders(testCase)
            import matlab.unittest.fixtures.TemporaryFolderFixture

            testCase.DataRoot = testCase.applyFixture(TemporaryFolderFixture).Folder;
            testCase.DataDir = testCase.DataRoot;
            testCase.SaveDir = testCase.applyFixture(TemporaryFolderFixture).Folder;
        end
    end

    methods (Test)
        function testTriggeredTrials(testCase)
            nLines = [100000 120000 110000];
            [dmd1, dmd2] = testCase.writeTriggeredFiles(nLines, nLines);
            testCase.writeReferenceStacks();

            tt = buildTrialTableSLAP2(testCase.DataRoot, testCase.SaveDir, true);

            testCase.verifyEqual(tt.filename, [dmd1; dmd2]);
            testCase.verifyEqual(tt.epoch, ones(2, 3));
            testCase.verifyEqual(tt.true_trial_ix, repmat(1:3, 2, 1));
            testCase.verifyEqual(tt.slap2_info.first_line, ones(2, 3));
            testCase.verifyEqual(tt.slap2_info.last_line, repmat(nLines, 2, 1));
            testCase.verifyEqual(tt.slap2_info.line_range_convention, 'inclusive');

            endTimes = testCase.datenums(dmd1);
            testCase.verifyEqual(tt.slap2_info.trial_end_time_from_pc, ...
                endTimes, 'AbsTol', 1e-9);
            testCase.verifyEqual(tt.slap2_info.trial_start_time_inferred, ...
                endTimes - nLines*testCase.LinePeriod_s/86400, 'AbsTol', 1e-9);
        end

        function testTriggeredTrialLineMismatch(testCase)
            % DMD1 failed to increment its trial number, so its second file
            % contains DMD2's second and third trials back to back.
            [dmd1, dmd2] = testCase.writeTriggeredFiles( ...
                [100000 220000], [100000 100000 120000]);
            testCase.writeReferenceStacks();

            tt = buildTrialTableSLAP2(testCase.DataRoot, testCase.SaveDir, true);

            testCase.verifyEqual(tt.filename, ...
                [dmd1([1 2 2]); dmd2([1 2 3])]);
            testCase.verifyEqual(tt.slap2_info.first_line, ...
                [1 1 100001; 1 1 1]);
            testCase.verifyEqual(tt.slap2_info.last_line, ...
                [100000 100000 220000; 100000 100000 120000]);

            dn1 = testCase.datenums(dmd1);
            dn2 = testCase.datenums(dmd2);
            testCase.verifyEqual(tt.slap2_info.trial_end_time_from_pc, ...
                [dn1(1) dn2(2) dn1(2)], 'AbsTol', 1e-9);
        end

        function testContinuousCycleFilesUseInclusiveNonoverlappingRanges(testCase)
            nLines = 450000;
            names = {'acq_DMD1-CYCLE-000000.dat', ...
                'acq_DMD2-CYCLE-000000.dat'};
            testCase.writeDat(names{1}, nLines, testCase.StartTime);
            testCase.writeDat(names{2}, nLines, testCase.StartTime);

            % Later CYCLE files must be ignored. Their invalid contents make
            % this test fail if the production function tries to read them.
            testCase.writeText(testCase.DataDir, ...
                'acq_DMD1-CYCLE-000001.dat', 'not a line count');
            testCase.writeText(testCase.DataDir, ...
                'acq_DMD2-CYCLE-000001.dat', 'not a line count');
            testCase.writeReferenceStacks();

            tt = buildTrialTableSLAP2(testCase.DataRoot, testCase.SaveDir, true);

            firstLines = [1 150001 300001];
            lastLines = [150000 300000 450000];
            testCase.verifyEqual(tt.filename, repmat(names', 1, 3));
            testCase.verifyEqual(tt.true_trial_ix, repmat(1:3, 2, 1));
            testCase.verifyEqual(tt.slap2_info.first_line, ...
                repmat(firstLines, 2, 1));
            testCase.verifyEqual(tt.slap2_info.last_line, ...
                repmat(lastLines, 2, 1));
            testCase.verifyEqual( ...
                tt.slap2_info.first_line(:, 2:end), ...
                tt.slap2_info.last_line(:, 1:end-1) + 1);
            testCase.verifyEqual(sum(lastLines - firstLines + 1), nLines);

            dn = testCase.datenums(names(1));
            toDays = testCase.LinePeriod_s/86400;
            testCase.verifyEqual(tt.slap2_info.trial_end_time_from_pc, ...
                dn - (nLines - lastLines)*toDays, 'AbsTol', 1e-9);
            testCase.verifyEqual(tt.slap2_info.trial_start_time_inferred, ...
                dn - (nLines - firstLines)*toDays, 'AbsTol', 1e-9);
        end

        function testContinuousCycleBoundaryLengths(testCase)
            lineCounts = [1 199999 200000 200001 399999 400000 400001];

            for caseIdx = 1:numel(lineCounts)
                caseRoot = fullfile(testCase.DataRoot, sprintf('case_%d', caseIdx));
                caseSave = fullfile(testCase.SaveDir, sprintf('case_%d', caseIdx));
                mkdir(caseRoot);
                mkdir(caseSave);

                nLines = lineCounts(caseIdx);
                testCase.writeDatIn(caseRoot, 'acq_DMD1-CYCLE-000000.dat', ...
                    nLines, testCase.StartTime);
                testCase.writeDatIn(caseRoot, 'acq_DMD2-CYCLE-000000.dat', ...
                    nLines, testCase.StartTime);
                testCase.writeReferenceStacksIn(caseRoot);

                tt = buildTrialTableSLAP2(caseRoot, caseSave, true);
                first = tt.slap2_info.first_line(1, :);
                last = tt.slap2_info.last_line(1, :);

                testCase.verifyEqual(numel(first), ceil(nLines/200000), ...
                    sprintf('Unexpected trial count for %d lines.', nLines));
                testCase.verifyEqual(first(1), 1);
                testCase.verifyEqual(last(end), nLines);
                testCase.verifyEqual(first(2:end), last(1:end-1) + 1);
                testCase.verifyEqual(sum(last - first + 1), nLines);
            end
        end

        function testContinuousUsesMinimumPathLineCount(testCase)
            testCase.writeDat('acq_DMD1-CYCLE-000000.dat', 250000, ...
                testCase.StartTime);
            testCase.writeDat('acq_DMD2-CYCLE-000000.dat', 225000, ...
                testCase.StartTime);
            testCase.writeReferenceStacks();

            tt = buildTrialTableSLAP2(testCase.DataRoot, testCase.SaveDir, true);

            testCase.verifyEqual(tt.slap2_info.last_line(:, end), [225000; 225000]);
            testCase.verifyEqual(sum(tt.slap2_info.last_line(1, :) - ...
                tt.slap2_info.first_line(1, :) + 1), 225000);
        end

        function testUnequalContinuousSourceCountsFail(testCase)
            testCase.writeDat('acqA_DMD1-CYCLE-000000.dat', 100000, ...
                testCase.StartTime);
            testCase.writeDat('acqB_DMD1-CYCLE-000000.dat', 100000, ...
                testCase.StartTime + minutes(1));
            testCase.writeDat('acqA_DMD2-CYCLE-000000.dat', 100000, ...
                testCase.StartTime);
            testCase.writeReferenceStacks();

            testCase.verifyError(@() buildTrialTableSLAP2( ...
                testCase.DataRoot, testCase.SaveDir, true), ?MException);
        end

        function testAindDynamicDataLayout(testCase)
            dynamicDir = fullfile(testCase.DataRoot, 'dynamic_data');
            mkdir(dynamicDir);
            testCase.DataDir = dynamicDir;
            cleanup = onCleanup(@() testCase.restoreDataDir()); %#ok<NASGU>

            [dmd1, dmd2] = testCase.writeTriggeredFiles(100000, 100000);
            testCase.writeReferenceStacksIn(testCase.DataRoot);

            tt = buildTrialTableSLAP2(testCase.DataRoot, testCase.SaveDir, true);

            testCase.verifyEqual(tt.datadr, dynamicDir);
            testCase.verifyEqual(tt.filename, [dmd1; dmd2]);
            testCase.verifyTrue(isfile(fullfile(testCase.SaveDir, 'trial_table.h5')));
        end

        function testReferenceStackMetadata(testCase)
            testCase.writeTriggeredFiles(100000, 100000);
            testCase.writeReferenceStacks();

            tt = buildTrialTableSLAP2(testCase.DataRoot, testCase.SaveDir, true);

            for pathName = {'Path1', 'Path2'}
                ref = tt.slap2_info.ref_stack.(pathName{1});
                testCase.verifyEqual(ref.channels, [1 2]);
                testCase.verifyEqual(ref.Zs, [0 1 2]);
                testCase.verifyEqual(ref.dmdPixel2SampleTransform, eye(3));
                testCase.verifySize(ref.IM, [8 8 6]);
            end
        end

        function testConfig1ReferencePreferredWhenMultipleReferencesExist(testCase)
            testCase.writeTriggeredFiles(100000, 100000);
            refDir = fullfile(testCase.DataRoot, 'reference');
            mkdir(refDir);
            for dmd = 1:2
                testCase.touch(refDir, sprintf('old_DMD%d-REFERENCE.tif', dmd));
                testCase.touch(refDir, ...
                    sprintf('selected_DMD%d_CONFIG1-REFERENCE.tif', dmd));
            end

            tt = buildTrialTableSLAP2(testCase.DataRoot, testCase.SaveDir, true);

            testCase.verifyTrue(isfield(tt.slap2_info.ref_stack, 'Path1'));
            testCase.verifyTrue(isfield(tt.slap2_info.ref_stack, 'Path2'));
        end

        function testTrialTableH5IsWrittenAndRoundTrips(testCase)
            [dmd1, dmd2] = testCase.writeTriggeredFiles( ...
                [100000 120000], [100000 120000]);
            testCase.writeReferenceStacks();

            buildTrialTableSLAP2(testCase.DataRoot, testCase.SaveDir, true);

            h5fn = fullfile(testCase.SaveDir, 'trial_table.h5');
            testCase.assertTrue(isfile(h5fn), 'trial_table.h5 was not written.');
            tt = loadStructFromH5(h5fn);
            testCase.verifyEqual(tt.datadr, testCase.DataDir);
            testCase.verifyEqual(tt.savedr, testCase.SaveDir);
            testCase.verifyEqual(tt.filename, [dmd1; dmd2]);
            testCase.verifyEqual(double(tt.slap2_info.first_line), ...
                [1 1; 1 1]);
            testCase.verifyEqual(double(tt.slap2_info.last_line), ...
                [100000 120000; 100000 120000]);
            testCase.verifyEqual(char(tt.slap2_info.line_range_convention), ...
                'inclusive');
            testCase.verifyTrue(isfield(tt.slap2_info.ref_stack, 'Path1'));
            testCase.verifyTrue(isfield(tt.slap2_info.ref_stack, 'Path2'));
        end

        function testNoDatFilesError(testCase)
            testCase.writeReferenceStacks();

            testCase.verifyError(@() buildTrialTableSLAP2( ...
                testCase.DataRoot, testCase.SaveDir, true), ...
                'buildTrialTableSLAP2:NoDatFiles');
        end

        function testNoReferenceStackError(testCase)
            testCase.writeTriggeredFiles(100000, 100000);

            testCase.verifyError(@() buildTrialTableSLAP2( ...
                testCase.DataRoot, testCase.SaveDir, true), ?MException);
        end

        function testAmbiguousConfig1ReferenceStackError(testCase)
            testCase.writeTriggeredFiles(100000, 100000);
            refDir = fullfile(testCase.DataRoot, 'reference');
            mkdir(refDir);
            for dmd = 1:2
                testCase.touch(refDir, sprintf('a_DMD%d_CONFIG1-REFERENCE.tif', dmd));
                testCase.touch(refDir, sprintf('b_DMD%d_CONFIG1-REFERENCE.tif', dmd));
            end

            testCase.verifyError(@() buildTrialTableSLAP2( ...
                testCase.DataRoot, testCase.SaveDir, true), ?MException);
        end

        function testUnalignedDmdsError(testCase)
            testCase.writeTriggeredFiles(100000, 150000);
            testCase.writeReferenceStacks();

            testCase.verifyError(@() buildTrialTableSLAP2( ...
                testCase.DataRoot, testCase.SaveDir, true), ?MException);
        end

        function testTriggeredAlignmentDifferenceBelowThresholdSucceeds(testCase)
            testCase.writeTriggeredFiles(100000, 101999);
            testCase.writeReferenceStacks();

            tt = buildTrialTableSLAP2(testCase.DataRoot, testCase.SaveDir, true);

            testCase.verifyEqual(tt.slap2_info.last_line(:, 1), [100000; 100000]);
        end

        function testTriggeredAlignmentDifferenceAtThresholdFails(testCase)
            testCase.writeTriggeredFiles(100000, 102000);
            testCase.writeReferenceStacks();

            % The production comparison is strict: difference < 2000.
            testCase.verifyError(@() buildTrialTableSLAP2( ...
                testCase.DataRoot, testCase.SaveDir, true), ?MException);
        end
    end

    methods (Access = private)
        function [dmd1, dmd2] = writeTriggeredFiles(testCase, nLines1, nLines2)
            nLines1 = reshape(nLines1, 1, []);
            nLines2 = reshape(nLines2, 1, []);
            dmd1 = arrayfun(@(k) sprintf('acq_DMD1-TRIAL%06d.dat', k), ...
                1:numel(nLines1), 'UniformOutput', false);
            dmd2 = arrayfun(@(k) sprintf('acq_DMD2-TRIAL%06d.dat', k), ...
                1:numel(nLines2), 'UniformOutput', false);

            for k = 1:numel(nLines1)
                testCase.writeDat(dmd1{k}, nLines1(k), ...
                    testCase.StartTime + minutes(k));
            end
            for k = 1:numel(nLines2)
                testCase.writeDat(dmd2{k}, nLines2(k), ...
                    testCase.StartTime + minutes(k));
            end
        end

        function writeDat(testCase, name, nLines, modificationTime)
            testCase.writeDatIn(testCase.DataDir, name, nLines, modificationTime);
        end

        function writeDatIn(testCase, folder, name, nLines, modificationTime)
            fn = testCase.writeText(folder, name, sprintf('%d', nLines));
            java.io.File(fn).setLastModified(int64(posixtime(modificationTime)*1000));
        end

        function fn = writeText(~, folder, name, contents)
            fn = fullfile(folder, name);
            fid = fopen(fn, 'w');
            assert(fid >= 0, 'Could not create test fixture: %s', fn);
            cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
            fprintf(fid, '%s', contents);
        end

        function writeReferenceStacks(testCase)
            testCase.writeReferenceStacksIn(testCase.DataRoot);
        end

        function writeReferenceStacksIn(testCase, root)
            refDir = fullfile(root, 'reference');
            if ~isfolder(refDir)
                mkdir(refDir);
            end
            for dmd = 1:2
                testCase.touch(refDir, ...
                    sprintf('acq_DMD%d_CONFIG1-REFERENCE.tif', dmd));
            end
        end

        function touch(~, folder, name)
            fn = fullfile(folder, name);
            fid = fopen(fn, 'w');
            assert(fid >= 0, 'Could not create test fixture: %s', fn);
            fclose(fid);
        end

        function dn = datenums(testCase, names)
            dn = zeros(1, numel(names));
            for k = 1:numel(names)
                d = dir(fullfile(testCase.DataDir, names{k}));
                dn(k) = d.datenum;
            end
        end

        function restoreDataDir(testCase)
            testCase.DataDir = testCase.DataRoot;
        end
    end
end