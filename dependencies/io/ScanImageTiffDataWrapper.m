function stack = ScanImageTiffDataWrapper(A, tifFile)
%SCANIMAGETIFFDATAWRAPPER Read TIFF stack via ScanImageTiffReader, with fallback.
%
% stack = ScanImageTiffDataWrapper(A, tifFile)
%
% Inputs
%   A       - ScanImageTiffReader object
%   tifFile - path to TIFF file used to construct A
%
% Behavior
%   1) Tries:
%        stack = A.data();
%   2) If that fails, reads the TIFF stack using MATLAB built-ins.
%
% Notes
%   - Returns stack in native on-disk datatype.
%   - Assumes a TIFF stack (multiple IFDs/pages).
%   - Supports grayscale and multi-sample pages.
%
% Example
%   A = ScanImageTiffReader(fn);
%   IM = ScanImageTiffDataWrapper(A, fn);

    try
        stack = A.data();
        return
    catch ME
        warning('ScanImageTiffDataWrapper:Fallback', ...
            'A.data() failed (%s). Falling back to built-in TIFF reader.', ...
            ME.message);
    end

    stack = readTiffStackFallback(tifFile);
end


function stack = readTiffStackFallback(tifFile)
%READTIFFSTACKFALLBACK Read all pages of a TIFF stack using Tiff/imread.

    info = imfinfo(tifFile);
    nFrames = numel(info);

    if nFrames == 0
        error('safeScanImageData:EmptyTiff', 'No TIFF frames found in file: %s', tifFile);
    end

    % Read first frame to determine output size/class.
    firstFrame = imread(tifFile, 1, 'Info', info);

    % Handle grayscale or multi-sample images.
    frameSize = size(firstFrame);
    frameClass = class(firstFrame);

    if ismatrix(firstFrame)
        % H x W x N
        stack = zeros(frameSize(2), frameSize(1), nFrames, frameClass);
        stack(:, :, 1) = permute(firstFrame,[2 1]);

        for k = 2:nFrames
            stack(:, :, k) = permute(imread(tifFile, k, 'Info', info), [2 1]);
        end
    else
        % H x W x C x N
        stack = zeros(frameSize(1), frameSize(2), frameSize(3), nFrames, frameClass);
        stack(:, :, :, 1) = permute(firstFrame,[2 1 3]);

        for k = 2:nFrames
            stack(:, :, :, k) = permute(imread(tifFile, k, 'Info', info), [2 1 3]);
        end
    end
end