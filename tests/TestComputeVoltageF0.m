classdef TestComputeVoltageF0 < matlab.unittest.TestCase
    %TESTCOMPUTEVOLTAGEF0 Characterize baseline values, shapes, and metadata.

    methods (TestClassSetup)
        function addProductionPaths(testCase)
            import matlab.unittest.fixtures.PathFixture

            testsDir = fileparts(mfilename('fullpath'));
            repoRoot = fileparts(testsDir);
            testCase.applyFixture(PathFixture(fullfile(repoRoot, 'source_extraction')));
            testCase.applyFixture(PathFixture(fullfile(repoRoot, 'dependencies', 'gui')));
        end
    end

    methods (Test)
        function testStaticPercentileIgnoresNonfiniteSamples(testCase)
            params = testCase.params('static', 50, 1, 1, 'single');
            raw = single([1 NaN 2 Inf 3 -Inf]);

            [f0, meta] = computeVoltageF0(raw, 1000, params);

            testCase.verifyEqual(f0, single(2 * ones(size(raw))));
            testCase.verifyEqual(meta.method, 'static_percentile');
            testCase.verifyEqual(meta.percentile, 50);
            testCase.verifyEqual(meta.sampleRateHz, 1000);
            testCase.verifyFalse(meta.timeVarying);
        end

        function testStaticPreservesRowAndColumnOrientation(testCase)
            params = testCase.params('static', 50, 1, 1, 'single');
            row = single([1 2 3]);
            column = row.';

            rowF0 = computeVoltageF0(row, 10, params);
            columnF0 = computeVoltageF0(column, 10, params);

            testCase.verifySize(rowF0, [1 3]);
            testCase.verifySize(columnF0, [3 1]);
            testCase.verifyEqual(rowF0, single([2 2 2]));
            testCase.verifyEqual(columnF0, single([2; 2; 2]));
        end

        function testMatrixInputIsFlattenedToAColumn(testCase)
            params = testCase.params('static', 50, 1, 1, 'single');

            f0 = computeVoltageF0(single([1 3; 2 4]), 10, params);

            testCase.verifySize(f0, [4 1]);
            testCase.verifyEqual(f0, single(2.5 * ones(4, 1)));
        end

        function testPrecisionControlsOutputClass(testCase)
            raw = uint16([2 4 6]);
            singleParams = testCase.params('static', 50, 1, 1, 'single');
            doubleParams = testCase.params('static', 50, 1, 1, 'double');

            singleF0 = computeVoltageF0(raw, 10, singleParams);
            doubleF0 = computeVoltageF0(raw, 10, doubleParams);

            testCase.verifyClass(singleF0, 'single');
            testCase.verifyClass(doubleF0, 'double');
            testCase.verifyEqual(singleF0, single([4 4 4]));
            testCase.verifyEqual(doubleF0, [4 4 4]);
        end

        function testZeroBaselineUsesMedianAbsoluteFallback(testCase)
            params = testCase.params('static', 50, 1, 1, 'single');
            raw = single([-2 0 2]);

            f0 = computeVoltageF0(raw, 10, params);

            testCase.verifyEqual(f0, single([2 2 2]));
        end

        function testAllNonfiniteAndAllZeroInputsUseUnitFallback(testCase)
            params = testCase.params('static', 50, 1, 1, 'single');

            nonfinite = computeVoltageF0(single([NaN Inf -Inf]), 10, params);
            zerosF0 = computeVoltageF0(single(zeros(2, 1)), 10, params);

            testCase.verifyEqual(nonfinite, single([1 1 1]));
            testCase.verifyEqual(zerosF0, single(ones(2, 1)));
        end

        function testEmptyInputReturnsBeforeSampleRateValidation(testCase)
            params = testCase.params('robust', 50, 1, 3, 'double');
            raw = single(zeros(1, 0));

            [f0, meta] = computeVoltageF0(raw, -1, params);

            testCase.verifySize(f0, [1 0]);
            testCase.verifyClass(f0, 'double');
            testCase.verifyEqual(meta, struct( ...
                'method', 'robust', 'sampleRateHz', -1));
        end

        function testRobustSingleBinFallsBackToStaticMetadata(testCase)
            params = testCase.params('robust', 50, 10, 30, 'single');

            [f0, meta] = computeVoltageF0(single([2 4 6]), 1, params);

            testCase.verifyEqual(f0, single([4 4 4]));
            testCase.verifyEqual(meta.method, 'static_percentile');
            testCase.verifyFalse(meta.timeVarying);
            testCase.verifyFalse(isfield(meta, 'n_bins'));
        end

        function testRobustInterpolationAndEndpointExtension(testCase)
            params = testCase.params('robust', 50, 1, 1, 'single');
            raw = single([10 10 20 20]);

            [f0, meta] = computeVoltageF0(raw, 2, params);

            testCase.verifyEqual(f0, single([10 12.5 17.5 20]), ...
                'AbsTol', single(1e-6));
            testCase.verifyEqual(meta.method, ...
                'robust_binned_percentile_moving_median');
            testCase.verifyEqual(meta.percentile, 50);
            testCase.verifyEqual(meta.bin_s, 1);
            testCase.verifyEqual(meta.smooth_s, 1);
            testCase.verifyEqual(meta.bin_samples, 2);
            testCase.verifyEqual(meta.smooth_bins, 1);
            testCase.verifyEqual(meta.n_bins, 2);
            testCase.verifyEqual(meta.sampleRateHz, 2);
            testCase.verifyTrue(meta.timeVarying);
        end

        function testRobustMovingMedianRoundsEvenWindowUpToOdd(testCase)
            params = testCase.params('robust', 50, 1, 2, 'single');
            raw = single([1 100 3 4]);

            [f0, meta] = computeVoltageF0(raw, 1, params);

            testCase.verifyEqual(meta.smooth_bins, 3);
            testCase.verifyEqual(f0, single([50.5 3 4 3.5]), ...
                'AbsTol', single(1e-6));
        end

        function testRobustMissingBinsAreLinearlyFilled(testCase)
            params = testCase.params('robust', 50, 1, 1, 'single');

            f0 = computeVoltageF0(single([1 NaN 3]), 1, params);

            testCase.verifyEqual(f0, single([1 2 3]), ...
                'AbsTol', single(1e-6));
        end

        function testRobustMissingEndpointBinsUseConstantExtension(testCase)
            params = testCase.params('robust', 50, 1, 1, 'single');

            f0 = computeVoltageF0(single([NaN 1 NaN 3 NaN]), 1, params);

            testCase.verifyEqual(f0, single([1 1 2 3 3]), ...
                'AbsTol', single(1e-6));
        end

        function testRobustPartialFinalBinMetadata(testCase)
            params = testCase.params('robust', 50, 2, 2, 'double');

            [f0, meta] = computeVoltageF0(single([1 1 1 5 5]), 2, params);

            testCase.verifyClass(f0, 'double');
            testCase.verifySize(f0, [1 5]);
            testCase.verifyEqual(meta.bin_samples, 4);
            testCase.verifyEqual(meta.n_bins, 2);
            testCase.verifyEqual(f0([1 end]), [1 5], 'AbsTol', 1e-6);
        end

        function testDefaultParametersAreUsedWhenOmitted(testCase)
            [f0, meta] = computeVoltageF0(single(7 * ones(1, 20)), 10);

            testCase.verifyEqual(f0, single(7 * ones(1, 20)));
            testCase.verifyClass(f0, 'single');
            testCase.verifyEqual(meta.method, 'static_percentile');
            testCase.verifyEqual(meta.percentile, 50);
        end

        function testUnknownMethodError(testCase)
            params = struct('f0Method', 'unknown', 'precision', 'single');
            testCase.verifyError(@() computeVoltageF0(single(1), 1, params), ...
                'computeVoltageF0:UnknownMethod');
        end

        function testInvalidNonemptySampleRatesFailValidation(testCase)
            params = testCase.params('static', 50, 1, 1, 'single');
            invalidRates = {0, -1, NaN, Inf, [1 2], 1 + 1i, '10'};
            for idx = 1:numel(invalidRates)
                rate = invalidRates{idx};
                testCase.verifyError(@() computeVoltageF0(single(1), ...
                    rate, params), ?MException);
            end
        end
    end

    methods (Static, Access = private)
        function params = params(method, percentile, binSeconds, smoothSeconds, precision)
            params = struct( ...
                'f0Method', method, ...
                'f0Percentile', percentile, ...
                'f0Bin_s', binSeconds, ...
                'f0Smooth_s', smoothSeconds, ...
                'precision', precision);
        end
    end
end