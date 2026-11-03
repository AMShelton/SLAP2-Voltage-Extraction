classdef TestHdf5StructIO < matlab.unittest.TestCase
    %TESTHDF5STRUCTIO Tests for saveStructToH5 and loadStructFromH5.

    properties
        TemporaryFolder
        H5File
    end

    methods (TestClassSetup)
        function addIoPath(testCase)
            import matlab.unittest.fixtures.PathFixture

            testsDir = fileparts(mfilename('fullpath'));
            repoRoot = fileparts(testsDir);
            testCase.applyFixture(PathFixture( ...
                fullfile(repoRoot, 'dependencies', 'io')));
        end
    end

    methods (TestMethodSetup)
        function makeTemporaryFile(testCase)
            import matlab.unittest.fixtures.TemporaryFolderFixture

            testCase.TemporaryFolder = ...
                testCase.applyFixture(TemporaryFolderFixture).Folder;
            testCase.H5File = fullfile(testCase.TemporaryFolder, 'values.h5');
        end
    end

    methods (Test)
        function testNestedNumericAndLogicalRoundTrip(testCase)
            input = struct();
            input.doubleMatrix = reshape(1:12, 3, 4);
            input.singleCube = reshape(single(1:24), 2, 3, 4);
            input.uint16Row = uint16([0 1 65535]);
            input.int32Column = int32([-2; 0; 7]);
            input.flags = logical([1 0; 0 1]);
            input.nested = struct('scalar', int8(-3), ...
                'vector', uint64([1 2 3]));

            saveStructToH5(input, testCase.H5File);
            actual = loadStructFromH5(testCase.H5File);

            testCase.verifyEqual(actual.doubleMatrix, input.doubleMatrix);
            testCase.verifyEqual(actual.singleCube, input.singleCube);
            testCase.verifyEqual(actual.uint16Row, input.uint16Row);
            testCase.verifyEqual(actual.int32Column, input.int32Column);
            testCase.verifyEqual(actual.flags, int8(input.flags));
            testCase.verifyEqual(actual.nested.scalar, input.nested.scalar);
            testCase.verifyEqual(actual.nested.vector, input.nested.vector);
        end

        function testTextAndCellShapesRoundTrip(testCase)
            input = struct();
            input.title = 'voltage extraction';
            input.label = "single string";
            input.labels = ["alpha" "beta"; "gamma" "delta"];
            input.notes = {'one', "two"; '', []};
            input.filename = {'only.dat'};
            input.fn_raw = {'a.dat', 'b.dat'; 'c.dat', 'd.dat'};

            saveStructToH5(input, testCase.H5File);
            actual = loadStructFromH5(testCase.H5File);

            testCase.verifyEqual(actual.title, input.title);
            testCase.verifyEqual(actual.label, char(input.label));
            testCase.verifyEqual(actual.labels, cellstr(input.labels));
            testCase.verifyEqual(actual.notes, {'one', 'two'; '', ''});
            testCase.verifyEqual(actual.filename, input.filename);
            testCase.verifyEqual(actual.fn_raw, input.fn_raw);
        end

        function testDatasetDimensionsAndLayoutMarker(testCase)
            input = struct();
            input.matrix = reshape(uint16(1:24), 2, 3, 4);
            input.filename = {'a', 'b', 'c'};

            saveStructToH5(input, testCase.H5File);

            matrixInfo = h5info(testCase.H5File, '/matrix');
            filenameInfo = h5info(testCase.H5File, '/filename');
            testCase.verifyEqual(double(matrixInfo.Dataspace.Size), [2 3 4]);
            testCase.verifyEqual(double(filenameInfo.Dataspace.Size), [1 3]);
            testCase.verifyEqual(h5read(testCase.H5File, '/row_major'), uint8(0));
        end

        function testEmptyValuesAreSkipped(testCase)
            input = struct();
            input.emptyNumeric = [];
            input.emptyCell = {};
            input.present = uint8(9);

            saveStructToH5(input, testCase.H5File);
            actual = loadStructFromH5(testCase.H5File);

            testCase.verifyFalse(isfield(actual, 'emptyNumeric'));
            testCase.verifyFalse(isfield(actual, 'emptyCell'));
            testCase.verifyEqual(actual.present, uint8(9));
            testCase.verifyEqual(actual.row_major, uint8(0));
        end

        function testExistingFileIsOverwritten(testCase)
            saveStructToH5(struct('oldValue', 1), testCase.H5File);
            saveStructToH5(struct('newValue', uint16(2)), testCase.H5File);

            actual = loadStructFromH5(testCase.H5File);
            testCase.verifyFalse(isfield(actual, 'oldValue'));
            testCase.verifyEqual(actual.newValue, uint16(2));
        end

        function testLegacyFieldNamesAreNormalized(testCase)
            input = struct();
            input.slap2_info.ref_stack.DMD1 = struct('channels', [1 2]);
            input.slap2_info.ref_stack.Path2 = struct('channels', 3);
            input.slap2.Z = [10 20];

            saveStructToH5(input, testCase.H5File);
            actual = loadStructFromH5(testCase.H5File);

            testCase.verifyFalse(isfield(actual.slap2_info.ref_stack, 'DMD1'));
            testCase.verifyEqual( ...
                actual.slap2_info.ref_stack.Path1.channels, [1 2]);
            testCase.verifyEqual( ...
                actual.slap2_info.ref_stack.Path2.channels, 3);
            testCase.verifyFalse(isfield(actual.slap2, 'Z'));
            testCase.verifyEqual(actual.slap2.Z_depths, [10 20]);
        end

        function testExistingNormalizedNamesTakePrecedence(testCase)
            input.slap2_info.ref_stack.DMD1 = uint8(1);
            input.slap2_info.ref_stack.Path1 = uint8(2);
            input.slap2.Z = 3;
            input.slap2.Z_depths = 4;

            saveStructToH5(input, testCase.H5File);
            actual = loadStructFromH5(testCase.H5File);

            testCase.verifyEqual(actual.slap2_info.ref_stack.Path1, uint8(2));
            testCase.verifyEqual(actual.slap2.Z, 3);
            testCase.verifyEqual(actual.slap2.Z_depths, 4);
        end

        function testSaveRejectsMissingFilename(testCase)
            testCase.verifyError(@() saveStructToH5(struct()), ...
                'saveStructToH5:MissingFilename');
            testCase.verifyError(@() saveStructToH5(struct(), ''), ...
                'saveStructToH5:MissingFilename');
        end

        function testSaveRejectsNonScalarStructInput(testCase)
            input = repmat(struct('value', 1), 1, 2);
            testCase.verifyError(@() saveStructToH5(input, testCase.H5File), ...
                'saveStructToH5:UnsupportedInput');
        end

        function testSaveRejectsNonScalarNestedStruct(testCase)
            input.items = repmat(struct('value', 1), 1, 2);
            testCase.verifyError(@() saveStructToH5(input, testCase.H5File), ...
                'saveStructToH5:NonScalarStruct');
        end

        function testSaveRejectsUnsupportedCellContents(testCase)
            input.values = {1, 2};
            testCase.verifyError(@() saveStructToH5(input, testCase.H5File), ...
                'saveStructToH5:UnsupportedCell');
        end

        function testSaveRejectsUnsupportedValueType(testCase)
            input.value = datetime(2024, 1, 1);
            testCase.verifyError(@() saveStructToH5(input, testCase.H5File), ...
                'saveStructToH5:UnsupportedType');
        end

        function testLoadRejectsMissingFilename(testCase)
            testCase.verifyError(@() loadStructFromH5(), ...
                'loadStructFromH5:MissingFilename');
            testCase.verifyError(@() loadStructFromH5(''), ...
                'loadStructFromH5:MissingFilename');
        end

        function testLoadRejectsMissingFile(testCase)
            missing = fullfile(testCase.TemporaryFolder, 'missing.h5');
            testCase.verifyError(@() loadStructFromH5(missing), ...
                'loadStructFromH5:FileNotFound');
        end
    end
end
