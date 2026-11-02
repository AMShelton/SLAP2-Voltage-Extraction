classdef TestTrace < matlab.unittest.TestCase
    %TESTTRACE Tests Trace metadata mapping with a concrete-compatible fake.

    properties
        TempDir
    end

    methods (TestClassSetup)
        function addTestAndProductionPackages(testCase)
            import matlab.unittest.fixtures.PathFixture

            testsDir = fileparts(mfilename('fullpath'));
            repoRoot = fileparts(testsDir);
            testCase.applyFixture(PathFixture( ...
                fullfile(repoRoot, 'dependencies', 'slap2_trace')));
            % This path supplies only the minimal slap2.util.MultiDataFiles
            % type required by Trace's argument and property declarations.
            testCase.applyFixture(PathFixture(fullfile(testsDir, 'fakes')));
        end
    end

    methods (TestMethodSetup)
        function makeTemporaryFolder(testCase)
            import matlab.unittest.fixtures.TemporaryFolderFixture

            testCase.TempDir = testCase.applyFixture( ...
                TemporaryFolderFixture).Folder;
        end
    end

    methods (Test)
        function testConstructorStoresTypedInputsAndDefaults(testCase)
            source = testCase.makeMappingSource();

            trace = slap2.util.datafile.trace.Trace(source);

            testCase.verifySameHandle(trace.hMultiDataFiles, source);
            testCase.verifyEqual(trace.zIdx, 1);
            testCase.verifyEqual(trace.chIdx, 1);
            testCase.verifyEmpty(trace.pixelIdxs);
            testCase.verifyEmpty(trace.superPixelIds);
        end

        function testNumericPixelListsCreateExpectedTracePixels(testCase)
            source = testCase.makeMappingSource();
            trace = slap2.util.datafile.trace.Trace(source, 1, 2);

            trace.setPixelIdxs([1 2], 7);

            testCase.verifyEqual(trace.pixelIdxs, uint32([1; 2; 7]));
            testCase.verifyEqual(trace.superPixelIds, [1 6]);
            testCase.verifyEqual( ...
                [trace.TracePixels.superPixelNumPixels], single([2 2]));
            testCase.verifyEqual( ...
                [trace.TracePixels.superPixelNumPixelsSelected], single([2 1]));
            testCase.verifyEqual(trace.TracePixels(1).lineIdxs, ...
                uint32([1 2 4]));
            testCase.verifyEqual(trace.TracePixels(1).byteOffsets, ...
                uint32([6 24 60]));
            testCase.verifyEqual(trace.TracePixels(2).lineIdxs, uint32(1));
            testCase.verifyEqual(trace.TracePixels(2).byteOffsets, uint32(10));
            testCase.verifyEqual(trace.TracePixels(1).fileNames, ...
                string({'first.dat', 'second.dat'}));
        end

        function testLogicalMapsAndTransposedMapMatchNumericIndices(testCase)
            source = testCase.makeMappingSource();
            fromMaps = slap2.util.datafile.trace.Trace(source);
            fromLists = slap2.util.datafile.trace.Trace(source);
            rasterMap = false(3, 2);
            rasterMap([1 2]) = true;
            integrationMap = false(3, 2);
            integrationMap(1) = true;

            fromMaps.setPixelIdxs(rasterMap, integrationMap');
            fromLists.setPixelIdxs([1 2], 7);

            testCase.verifyEqual(fromMaps.pixelIdxs, fromLists.pixelIdxs);
            testCase.verifyEqual(fromMaps.superPixelIds, fromLists.superPixelIds);
        end

        function testIncorrectLogicalMapSizeFails(testCase)
            trace = slap2.util.datafile.trace.Trace( ...
                testCase.makeMappingSource());

            failed = false;
            try
                trace.setPixelIdxs(false(4, 4), []);
            catch
                failed = true;
            end
            testCase.verifyTrue(failed, ...
                'An incorrectly sized logical map should fail.');
        end

        function testNonIntegerPixelListFailsValidation(testCase)
            trace = slap2.util.datafile.trace.Trace( ...
                testCase.makeMappingSource());

            testCase.verifyError(@() trace.setPixelIdxs(1.5, []), ...
                'MATLAB:expectedInteger');
        end

        function testUnknownPixelsAreRetainedAsRequestButNotTraces(testCase)
            trace = slap2.util.datafile.trace.Trace( ...
                testCase.makeMappingSource());

            trace.setPixelIdxs([1 99], []);

            testCase.verifyEqual(trace.pixelIdxs, uint32([1; 99]));
            testCase.verifyEqual(trace.superPixelIds, 1);
        end

        function testRepeatedSelectionDoesNotDuplicateTracePixels(testCase)
            trace = slap2.util.datafile.trace.Trace( ...
                testCase.makeMappingSource());

            trace.setPixelIdxs([1 2], 7);
            trace.setPixelIdxs([1 2], 7);

            testCase.verifyEqual(trace.superPixelIds, [1 6]);
            testCase.verifySize(trace.TracePixels, [2 1]);
        end

        function testLoadDataAndProcessDelegateToTracePixels(testCase)
            filename = testCase.writeInt16('trace.dat', ...
                int16(10 * ones(1, 8)));
            source = testCase.makeProcessingSource(filename);
            traceObject = slap2.util.datafile.trace.Trace(source);
            traceObject.setPixelIdxs(1, []);

            traceObject.loadData();
            [trace, weight] = traceObject.process(1, 1);

            testCase.verifyTrue(traceObject.TracePixels.isLoaded);
            testCase.verifyEqual(traceObject.TracePixels.data, ...
                single(10 * ones(2, 2)));
            testCase.verifyEqual(trace, single(10 * ones(4, 1)), ...
                'AbsTol', single(1e-5));
            testCase.verifyGreaterThan(weight, zeros(4, 1, 'single'));
        end
    end

    methods (Access = private)
        function source = makeMappingSource(~)
            values.header = struct( ...
                'dmdPixelsPerRow', 3, ...
                'dmdPixelsPerColumn', 2, ...
                'bytesPerCycle', 64, ...
                'firstCycleOffsetBytes', 2, ...
                'linesPerCycle', 4);
            values.zPixelReplacementMaps = {[ ...
                0 1; 1 1; 2 2; 3 3; 4 4; 5 5; ...
                0 6; 1 6; 2 7; 3 8; 4 9; 5 10]};
            values.hDataFiles = struct( ...
                'filename', {'first.dat', 'second.dat'});
            values.lineSuperPixelIDs = {uint32([1 2 6]), ...
                uint32([2 1]), uint32([6 1]), uint32(1)};
            values.lineFastZIdxs = [1 1 2 1];
            values.lineDataStartIdxs = [1 10 20 30];
            source = slap2.util.MultiDataFiles(values);
        end

        function source = makeProcessingSource(~, filename)
            values.header = struct( ...
                'dmdPixelsPerRow', 2, ...
                'dmdPixelsPerColumn', 2, ...
                'bytesPerCycle', 8, ...
                'firstCycleOffsetBytes', 0, ...
                'linesPerCycle', 2);
            values.zPixelReplacementMaps = {[0 1]};
            values.hDataFiles = struct('filename', filename);
            values.lineSuperPixelIDs = {uint32(1), uint32(1)};
            values.lineFastZIdxs = [1 1];
            values.lineDataStartIdxs = [1 3];
            source = slap2.util.MultiDataFiles(values);
        end

        function filename = writeInt16(testCase, name, values)
            filename = fullfile(testCase.TempDir, name);
            fid = fopen(filename, 'w');
            testCase.assertGreaterThanOrEqual(fid, 0, ...
                sprintf('Could not create fixture %s.', filename));
            cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
            count = fwrite(fid, values, 'int16');
            testCase.assertEqual(count, numel(values));
        end
    end
end
