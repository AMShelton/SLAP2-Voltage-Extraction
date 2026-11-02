classdef TestComputeVoltageDFF < matlab.unittest.TestCase
    %TESTCOMPUTEVOLTAGEDFF Characterize polarity, fallback, shape, and metadata.

    methods (TestClassSetup)
        function addProductionPath(testCase)
            import matlab.unittest.fixtures.PathFixture

            testsDir = fileparts(mfilename('fullpath'));
            repoRoot = fileparts(testsDir);
            testCase.applyFixture(PathFixture(fullfile(repoRoot, 'source_extraction')));
        end
    end

    methods (Test)
        function testAutoASAP8UsesIncreasingFormula(testCase)
            raw = single([100 110 90]);
            baseline = single([100 100 100]);

            [dff, meta] = computeVoltageDFF( ...
                raw, baseline, 'ASAP8', 'auto', 'single');

            testCase.verifyEqual(dff, single([0 0.1 -0.1]), ...
                'AbsTol', single(1e-6));
            testCase.verifyEqual(meta.indicatorName, 'ASAP8');
            testCase.verifyEqual(meta.indicatorDirectionRequested, 'auto');
            testCase.verifyEqual(meta.indicatorDirectionResolved, 'increases');
            testCase.verifyEqual(meta.directionSource, 'indicatorName');
            testCase.verifyEqual(meta.dffSign, 1);
            testCase.verifyEqual(meta.formula, 'dff = (F - F0) / F0');
        end

        function testAutoASAP7UsesDecreasingFormula(testCase)
            raw = single([100 90 110]);
            baseline = single([100 100 100]);

            [dff, meta] = computeVoltageDFF( ...
                raw, baseline, 'AsAp7y', 'auto', 'single');

            testCase.verifyEqual(dff, single([0 0.1 -0.1]), ...
                'AbsTol', single(1e-6));
            testCase.verifyEqual(meta.indicatorDirectionResolved, 'decreases');
            testCase.verifyEqual(meta.directionSource, 'indicatorName');
            testCase.verifyEqual(meta.dffSign, -1);
            testCase.verifyEqual(meta.formula, 'dff = (F0 - F) / F0');
        end

        function testExplicitIncreasingAliases(testCase)
            aliases = {'increases', 'increase', 'standard', 'positive', 'brightens'};
            for idx = 1:numel(aliases)
                [dff, meta] = computeVoltageDFF(single(12), single(10), ...
                    'unknown', aliases{idx}, 'single');
                testCase.verifyEqual(dff, single(0.2), ...
                    'AbsTol', single(1e-6));
                testCase.verifyEqual(meta.indicatorDirectionResolved, 'increases');
                testCase.verifyEqual(meta.directionSource, 'explicit');
                testCase.verifyEqual(meta.indicatorDirectionRequested, aliases{idx});
            end
        end

        function testExplicitDecreasingAliasesAndNormalization(testCase)
            aliases = {'decreases', 'decrease', 'inverted', 'negative', ...
                'quenched', 'quenching', ' DECREASE '};
            for idx = 1:numel(aliases)
                [dff, meta] = computeVoltageDFF(single(8), single(10), ...
                    'unknown', aliases{idx}, 'single');
                testCase.verifyEqual(dff, single(0.2), ...
                    'AbsTol', single(1e-6));
                testCase.verifyEqual(meta.indicatorDirectionResolved, 'decreases');
                testCase.verifyEqual(meta.directionSource, 'explicit');
                testCase.verifyEqual(meta.indicatorDirectionRequested, aliases{idx});
            end

            [dff, meta] = computeVoltageDFF(single(12), single(10), ...
                'unknown', 'brightens', 'single');
            testCase.verifyEqual(dff, single(0.2), 'AbsTol', single(1e-6));
            testCase.verifyEqual(meta.indicatorDirectionResolved, 'increases');
        end

        function testExplicitDirectionOverridesIndicatorName(testCase)
            [dff, meta] = computeVoltageDFF(single(12), single(10), ...
                'ASAP7', 'increases', 'single');

            testCase.verifyEqual(dff, single(0.2), 'AbsTol', single(1e-6));
            testCase.verifyEqual(meta.indicatorDirectionResolved, 'increases');
            testCase.verifyEqual(meta.directionSource, 'explicit');
        end

        function testDirectionTrimsWhitespaceAndIgnoresCase(testCase)
            [dff, meta] = computeVoltageDFF( ...
                single(12), single(10), '', ' PoSiTiVe ', 'single');

            testCase.verifyEqual(dff, single(0.2), ...
                'AbsTol', single(1e-6));
            testCase.verifyEqual(meta.indicatorDirectionResolved, 'increases');
            testCase.verifyEqual(meta.indicatorDirectionRequested, ' PoSiTiVe ');
        end

        function testEmbeddedHyphensAndSpacesAreInvalid(testCase)
            invalid = {'posi-tive', 'quench ing'};
            for idx = 1:numel(invalid)
                direction = invalid{idx};
                testCase.verifyError(@() computeVoltageDFF( ...
                    single(1), single(1), '', direction, 'single'), ...
                    'computeVoltageDFF:InvalidDirection');
            end
        end

        function testBadBaselinesUseMedianAbsoluteRawFallback(testCase)
            raw = single([2 4 6]);
            baseline = single([0 NaN Inf]);

            dff = computeVoltageDFF(raw, baseline, '', 'increases', 'single');

            testCase.verifyEqual(dff, single([-0.5 0 0.5]), ...
                'AbsTol', single(1e-6));
        end

        function testAllZeroRawUsesUnitFallback(testCase)
            dff = computeVoltageDFF(single([0 0]), single([0 NaN]), ...
                '', 'increases', 'single');

            testCase.verifyEqual(dff, single([-1 -1]));
        end

        function testNegativeFiniteBaselineIsNotReplaced(testCase)
            dff = computeVoltageDFF(single([-12 -8]), single([-10 -10]), ...
                '', 'increases', 'single');

            testCase.verifyEqual(dff, single([0.2 -0.2]), ...
                'AbsTol', single(1e-6));
        end

        function testRawNaNPropagatesToOutput(testCase)
            dff = computeVoltageDFF(single([10 NaN 12]), single([10 10 10]), ...
                '', 'increases', 'single');

            testCase.verifyEqual(dff([1 3]), single([0 0.2]), ...
                'AbsTol', single(1e-6));
            testCase.verifyTrue(isnan(dff(2)));
        end

        function testOutputPreservesMultidimensionalShape(testCase)
            raw = reshape(single(1:24), [2 3 4]);
            baseline = single(10 * ones(size(raw)));

            dff = computeVoltageDFF(raw, baseline, '', 'increases', 'single');

            testCase.verifySize(dff, [2 3 4]);
            testCase.verifyEqual(dff, (raw - 10) ./ 10, ...
                'AbsTol', single(1e-6));
        end

        function testPrecisionAndInputCastingBehavior(testCase)
            raw = uint16([10 12]);
            baseline = double([10 10]);

            asSingle = computeVoltageDFF( ...
                raw, baseline, '', 'increases', 'single');
            asDouble = computeVoltageDFF( ...
                raw, baseline, '', 'increases', 'double');
            unrecognizedPrecision = computeVoltageDFF( ...
                raw, baseline, '', 'increases', 'half');

            testCase.verifyClass(asSingle, 'single');
            testCase.verifyClass(asDouble, 'double');
            testCase.verifyClass(unrecognizedPrecision, 'single');
            testCase.verifyEqual(asSingle, single([0 0.2]), ...
                'AbsTol', single(1e-6));
            testCase.verifyEqual(asDouble, double(asSingle));
            testCase.verifyEqual(unrecognizedPrecision, asSingle);
        end

        function testEmptyInputsReturnEmptyWithMetadata(testCase)
            [dff, meta] = computeVoltageDFF(single(zeros(0, 1)), ...
                single(zeros(0, 1)), "ASAP8", "increases", "double");

            testCase.verifySize(dff, [0 1]);
            testCase.verifyClass(dff, 'double');
            testCase.verifyEqual(meta.indicatorName, 'ASAP8');
            testCase.verifyEqual(meta.indicatorDirectionRequested, 'increases');
            testCase.verifyEqual(meta.dffSign, 1);
        end

        function testOptionalArgumentsDefaultBeforeDirectionResolution(testCase)
            testCase.verifyError(@() computeVoltageDFF(single(1), single(1)), ...
                'computeVoltageDFF:UnknownIndicatorDirection');

            [dff, meta] = computeVoltageDFF(single(2), single(1), ...
                'ASAP8', [], []);
            testCase.verifyEqual(dff, single(1));
            testCase.verifyClass(dff, 'single');
            testCase.verifyEqual(meta.indicatorDirectionRequested, 'auto');
        end

        function testSizeMismatchError(testCase)
            mismatched = { ...
                {single([1 2]), single([1; 2])}, ...
                {single([1 2]), single(1)}, ...
                {single(ones(2, 2)), single(ones(2, 2, 1, 2))}};
            for idx = 1:numel(mismatched)
                inputs = mismatched{idx};
                testCase.verifyError(@() computeVoltageDFF( ...
                    inputs{1}, inputs{2}, '', 'increases', 'single'), ...
                    'computeVoltageDFF:SizeMismatch');
            end
        end

        function testUnknownAutoDirectionError(testCase)
            testCase.verifyError(@() computeVoltageDFF( ...
                single(1), single(1), 'unknown', 'auto', 'single'), ...
                'computeVoltageDFF:UnknownIndicatorDirection');
        end

        function testInvalidDirectionError(testCase)
            invalid = {'', 'sideways', 'increasing'};
            for idx = 1:numel(invalid)
                direction = invalid{idx};
                testCase.verifyError(@() computeVoltageDFF( ...
                    single(1), single(1), 'ASAP8', direction, 'single'), ...
                    'computeVoltageDFF:InvalidDirection');
            end
        end

        function testAutoPrefersASAP8WhenNameContainsBothFamilies(testCase)
            [dff, meta] = computeVoltageDFF(single(12), single(10), ...
                'ASAP7-ASAP8', 'auto', 'single');

            testCase.verifyEqual(dff, single(0.2), 'AbsTol', single(1e-6));
            testCase.verifyEqual(meta.indicatorDirectionResolved, 'increases');
        end
    end
end