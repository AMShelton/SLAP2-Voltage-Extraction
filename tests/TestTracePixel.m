classdef TestTracePixel < matlab.unittest.TestCase
    %TESTTRACEPIXEL Characterization tests for the vendored trace kernel.

    properties
        TempDir
    end

    methods (TestClassSetup)
        function addTraceKernel(testCase)
            import matlab.unittest.fixtures.PathFixture

            testsDir = fileparts(mfilename('fullpath'));
            repoRoot = fileparts(testsDir);
            testCase.applyFixture(PathFixture( ...
                fullfile(repoRoot, 'dependencies', 'slap2_trace')));
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
        function testLoadReadsOffsetsAcrossCyclesAndFiles(testCase)
            fileA = testCase.writeInt16('a.dat', int16([ ...
                11 99 intmin('int16') 88 21 77 31 66]));
            fileB = testCase.writeInt16('b.dat', int16([ ...
                -1 9 -2 8 -3 7 -4 6]));

            pixel = testCase.makePixel([string(fileA) string(fileB)], ...
                uint32([2 6]), ...
                uint32([1 3]));
            pixel = pixel.load();

            testCase.verifyTrue(pixel.isLoaded);
            testCase.verifyClass(pixel.data, 'single');
            testCase.verifyEqual(pixel.data, single([ ...
                11 21 -1 -3; 0 31 -2 -4]));
        end

        function testLoadIsIdempotentAfterFileChanges(testCase)
            filename = testCase.writeInt16('stable.dat', int16([ ...
                3 0 3 0 3 0 3 0]));
            pixel = testCase.makePixel(filename, uint32(2), uint32(1));
            pixel = pixel.load();
            original = pixel.data;

            testCase.writeInt16('stable.dat', int16(99 * ones(1, 8)));
            pixel = pixel.load();

            testCase.verifyEqual(pixel.data, original);
        end

        function testLoadReplacesInt16SentinelOnly(testCase)
            filename = testCase.writeInt16('sentinel.dat', int16([ ...
                intmin('int16') 0 intmax('int16') 0]));
            pixel = testCase.makePixel(filename, uint32([2 6]), ...
                uint32([1 2]));
            pixel.bytesPerCycle = 8;
            pixel = pixel.load();

            testCase.verifyEqual(pixel.data, ...
                single([0; intmax('int16')]));
        end

        function testProcessSinglePixelHasAnalyticalConstantResult(testCase)
            filename = testCase.writeInt16('constant.dat', ...
                int16(10 * ones(1, 8)));
            pixel = testCase.makePixel(filename, uint32([2 6]), ...
                uint32([2 4]));
            pixel.superPixelNumPixels = single(4);
            pixel.superPixelNumPixelsSelected = single(2);

            [pixel, trace, weighted, expected, expectedWeighted] = ...
                pixel.process(1, 1);

            sampled = [2 4 6 8];
            unsampled = setdiff(1:8, sampled);
            testCase.verifyTrue(pixel.isLoaded);
            testCase.verifySize(trace, [8 1]);
            testCase.verifyClass(trace, 'single');
            testCase.verifyEqual(trace(sampled), ...
                single(5 * ones(numel(sampled), 1)), 'AbsTol', single(1e-5));
            testCase.verifyEqual(trace(unsampled), ...
                zeros(numel(unsampled), 1, 'single'));
            testCase.verifyEqual(expected(sampled), ...
                single(10 * ones(numel(sampled), 1)));
            testCase.verifyGreaterThan(weighted, zeros(8, 1, 'single'));
            testCase.verifyGreaterThan(expectedWeighted(sampled), ...
                zeros(numel(sampled), 1, 'single'));
        end

        function testProcessAggregatesPixelsBeforeNormalization(testCase)
            first = testCase.loadedPixel(single(10), single(1/2));
            second = testCase.loadedPixel(single(20), single(1/2));

            [~, trace] = [first; second].process(1, 1);

            testCase.verifyEqual(trace, single(15 * ones(4, 1)), ...
                'AbsTol', single(1e-5));
        end

        function testProcessEmptyArrayReturnsEmptySingleColumns(testCase)
            pixels = slap2.util.datafile.trace.TracePixel.empty(0, 1);

            [pixels, trace, weighted, expected, expectedWeighted] = ...
                pixels.process(1, 1);

            testCase.verifyEmpty(pixels);
            testCase.verifySize(trace, [0 1]);
            testCase.verifyClass(trace, 'single');
            testCase.verifySize(weighted, [0 1]);
            testCase.verifySize(expected, [0 1]);
            testCase.verifySize(expectedWeighted, [0 1]);
        end
    end

    methods (Access = private)
        function pixel = makePixel(~, filenames, byteOffsets, lineIdxs)
            pixel = slap2.util.datafile.trace.TracePixel();
            pixel.fileNames = string(filenames);
            pixel.byteOffsets = byteOffsets;
            pixel.lineIdxs = lineIdxs;
            pixel.firstCycleOffsetBytes = 0;
            pixel.bytesPerCycle = 8;
            pixel.linesPerCycle = 4;
            pixel.superPixelNumPixels = single(1);
            pixel.superPixelNumPixelsSelected = single(1);
        end

        function pixel = loadedPixel(~, value, spatialWeight)
            pixel = slap2.util.datafile.trace.TracePixel();
            pixel.data = repmat(value, 2, 2);
            pixel.isLoaded = true;
            pixel.lineIdxs = uint32([1 2]);
            pixel.linesPerCycle = 2;
            pixel.superPixelNumPixels = single(1);
            pixel.superPixelNumPixelsSelected = spatialWeight;
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
