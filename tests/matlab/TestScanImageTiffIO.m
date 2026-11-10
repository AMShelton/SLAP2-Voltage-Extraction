classdef TestScanImageTiffIO < matlab.unittest.TestCase
    %TESTSCANIMAGETIFFIO Tests for the pure-MATLAB ScanImage TIFF helpers.

    properties
        TemporaryFolder
    end

    methods (TestClassSetup)
        function addIoPath(testCase)
            import matlab.unittest.fixtures.PathFixture

            testsDir = fileparts(mfilename('fullpath'));
            repoRoot = fileparts(fileparts(testsDir));
            testCase.applyFixture(PathFixture( ...
                fullfile(repoRoot, 'dependencies', 'io')));
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
        function testApiVersion(testCase)
            testCase.verifyEqual(ScanImageTiffReader.apiVersion(), ...
                'ScanImageTiffReader (pure MATLAB)');
        end

        function testConstructorOpensAndCloseIsIdempotent(testCase)
            filename = testCase.writeTiff(uint16(reshape(1:12, 3, 4)));
            reader = ScanImageTiffReader(filename);
            cleanup = onCleanup(@() delete(reader)); %#ok<NASGU>

            testCase.verifyTrue(reader.isOpen());
            reader.close();
            testCase.verifyFalse(reader.isOpen());
            reader.close();
            testCase.verifyFalse(reader.isOpen());
        end

        function testOpenOnDefaultConstructedReader(testCase)
            filename = testCase.writeTiff(uint8(reshape(1:20, 4, 5)));
            reader = ScanImageTiffReader();
            cleanup = onCleanup(@() delete(reader)); %#ok<NASGU>

            testCase.verifyFalse(reader.isOpen());
            returned = reader.open(filename);

            testCase.verifySameHandle(returned, reader);
            testCase.verifyTrue(reader.isOpen());
            testCase.verifyEqual(reader.data(), ...
                uint8(reshape(1:20, 4, 5)).');
        end

        function testReadsSinglePageUint8WithCurrentOrientation(testCase)
            frame = uint8([1 2 3 4; 11 12 13 14; 21 22 23 24]);
            filename = testCase.writeTiff(frame);
            reader = ScanImageTiffReader(filename);
            cleanup = onCleanup(@() delete(reader)); %#ok<NASGU>

            actual = reader.data();
            shape = reader.shape();

            testCase.verifyClass(actual, 'uint8');
            testCase.verifyEqual(actual, frame.');
            testCase.verifyEqual(shape.ndim, 2);
            testCase.verifyEqual(shape.dims, [4 3]);
            testCase.verifyEqual(shape.type, 0);
            testCase.verifyEqual(shape.strides, [1 4 12]);
        end

        function testReadsMultiPageUint16Stack(testCase)
            first = uint16([1 2 3 4; 5 6 7 8; 9 10 11 12]);
            second = first + 100;
            filename = testCase.writeTiff(cat(3, first, second));
            reader = ScanImageTiffReader(filename);
            cleanup = onCleanup(@() delete(reader)); %#ok<NASGU>

            actual = reader.data();
            expected = cat(3, first.', second.');
            shape = reader.shape();

            testCase.verifyClass(actual, 'uint16');
            testCase.verifyEqual(actual, expected);
            testCase.verifySize(actual, [4 3 2]);
            testCase.verifyEqual(shape.ndim, 3);
            testCase.verifyEqual(shape.dims, [4 3 2]);
            testCase.verifyEqual(shape.type, 1);
            testCase.verifyEqual(shape.strides, [1 4 12 24]);
        end

        function testDescriptionsAndMetadataForPlainTiff(testCase)
            filename = testCase.writeTiff(uint16(reshape(1:12, 3, 4)));
            reader = ScanImageTiffReader(filename);
            cleanup = onCleanup(@() delete(reader)); %#ok<NASGU>

            descriptions = reader.descriptions();
            testCase.verifySize(descriptions, [1 1]);
            testCase.verifyTrue(testCase.isSemanticallyEmptyText( ...
                descriptions{1}));
            % Keep this strict: char(0) is not empty and exposed the legacy
            % metadata misclassification tracked by the production issue.
            testCase.verifyEqual(reader.metadata(), '');
        end

        function testWrapperReturnsDataMetadataAndDescriptions(testCase)
            first = uint16([1 2 3; 4 5 6]);
            second = first + 10;
            filename = testCase.writeTiff(cat(3, first, second));

            [data, metadata, descriptions] = ScanImageTiffWrapper(filename);

            testCase.verifyEqual(data, cat(3, first.', second.'));
            testCase.verifyEqual(metadata, '');
            testCase.verifySize(descriptions, [2 1]);
            testCase.verifyTrue(all(cellfun( ...
                @(value) testCase.isSemanticallyEmptyText(value), ...
                descriptions)));
        end

        function testReadsValidatedLegacyMetadataTrailer(testCase)
            filename = testCase.writeTiff(uint16(reshape(1:12, 3, 4)));
            expected = sprintf('state.acq.numberOfFrames = 1\n');
            testCase.appendLegacyMetadata(filename, expected);

            reader = ScanImageTiffReader(filename);
            cleanup = onCleanup(@() delete(reader)); %#ok<NASGU>

            testCase.verifyEqual(reader.metadata(), expected);
        end

        function testRejectsNullOnlyLegacyMetadataCandidate(testCase)
            filename = testCase.writeTiff(uint16(reshape(1:12, 3, 4)));
            testCase.appendLegacyMetadata(filename, char(0));

            reader = ScanImageTiffReader(filename);
            cleanup = onCleanup(@() delete(reader)); %#ok<NASGU>

            testCase.verifyEqual(reader.metadata(), '');
        end

        function testRejectsImplausibleLegacyMetadataLength(testCase)
            filename = testCase.writeTiff(uint16(reshape(1:12, 3, 4)));
            fid = fopen(filename, 'a', 'ieee-le');
            testCase.assertGreaterThanOrEqual(fid, 0);
            fwrite(fid, intmax('uint32'), 'uint32');
            fclose(fid);

            reader = ScanImageTiffReader(filename);
            cleanup = onCleanup(@() delete(reader)); %#ok<NASGU>

            testCase.verifyEqual(reader.metadata(), '');
        end

        function testDataWrapperFallsBackAfterReaderIsClosed(testCase)
            first = uint16([1 2 3; 4 5 6]);
            second = first + 10;
            filename = testCase.writeTiff(cat(3, first, second));
            reader = ScanImageTiffReader(filename);
            reader.close();
            cleanup = onCleanup(@() delete(reader)); %#ok<NASGU>

            testCase.verifyWarning( ...
                @() ScanImageTiffDataWrapper(reader, filename), ...
                'ScanImageTiffDataWrapper:Fallback');

            warningState = warning('off', 'ScanImageTiffDataWrapper:Fallback');
            warningCleanup = onCleanup(@() warning(warningState)); %#ok<NASGU>
            actual = ScanImageTiffDataWrapper(reader, filename);
            testCase.verifyEqual(actual, cat(3, first.', second.'));
        end

        function testClosedReaderMethodsFail(testCase)
            filename = testCase.writeTiff(uint8(ones(2, 3)));
            reader = ScanImageTiffReader(filename);
            reader.close();
            cleanup = onCleanup(@() delete(reader)); %#ok<NASGU>

            testCase.verifyError(@() reader.data(), ...
                'ScanImageTiffReader:NotOpen');
            testCase.verifyError(@() reader.descriptions(), ...
                'ScanImageTiffReader:NotOpen');
            testCase.verifyError(@() reader.metadata(), ...
                'ScanImageTiffReader:NotOpen');
            testCase.verifyError(@() reader.shape(), ...
                'ScanImageTiffReader:NotOpen');
        end

        function testMissingFileFails(testCase)
            missing = fullfile(testCase.TemporaryFolder, 'missing.tif');
            testCase.verifyError(@() ScanImageTiffReader(missing), ...
                'ScanImageTiffReader:FileNotFound');
        end

        function testInvalidByteOrderMarkFails(testCase)
            filename = fullfile(testCase.TemporaryFolder, 'invalid.tif');
            fid = fopen(filename, 'w');
            testCase.assertGreaterThanOrEqual(fid, 0);
            fwrite(fid, uint8([0 1 2 3]), 'uint8');
            fclose(fid);

            testCase.verifyError(@() ScanImageTiffReader(filename), ...
                'ScanImageTiffReader:InvalidFile');
        end
    end

    methods (Access = private)
        function tf = isSemanticallyEmptyText(~, value)
            tf = isempty(value) || all(isspace(value));
        end

        function filename = writeTiff(testCase, stack)
            filename = fullfile(testCase.TemporaryFolder, ...
                sprintf('stack_%d.tif', randi(intmax('uint16'))));
            imwrite(stack(:, :, 1), filename, 'tif', 'Compression', 'none');
            for frameIndex = 2:size(stack, 3)
                imwrite(stack(:, :, frameIndex), filename, 'tif', ...
                    'WriteMode', 'append', 'Compression', 'none');
            end
        end

        function appendLegacyMetadata(testCase, filename, metadata)
            fid = fopen(filename, 'a', 'ieee-le');
            testCase.assertGreaterThanOrEqual(fid, 0);
            cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
            fwrite(fid, metadata, 'char');
            fwrite(fid, numel(metadata), 'uint32');
        end
    end
end
