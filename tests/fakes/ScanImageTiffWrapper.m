function [data, meta, desc] = ScanImageTiffWrapper(filename) %#ok<INUSD>
%SCANIMAGETIFFWRAPPER Deterministic reference-stack test double.
% The named TIFF only needs to exist; its contents are intentionally ignored.

data = reshape(uint16(1:(8*8*6)), 8, 8, 6);
meta = 'fake ScanImage metadata';
desc = cell(1, 6);

channels = [1 2 1 2 1 2];
zValues = [0 0 1 1 2 2];
for frameIdx = 1:6
    frame = struct( ...
        'channel', channels(frameIdx), ...
        'z', zValues(frameIdx), ...
        'dmdPixel2SampleTransform', eye(3));
    desc{frameIdx} = jsonencode(frame);
end
end