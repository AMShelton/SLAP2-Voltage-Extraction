function lineMask = expandMotionMaskToLines(maskSamples, lineIds, totalLines)
%EXPANDMOTIONMASKTOLINES Zero-order-hold a sampled mask onto every SLAP2 line.
%
% Sample k covers lines lineIds(k) .. lineIds(k+1)-1; the last sample runs to
% totalLines, and lines before lineIds(1) take the first sample's value.

maskSamples = logical(maskSamples(:));
lineIds = double(lineIds(:));
if numel(maskSamples) ~= numel(lineIds)
    error('expandMotionMaskToLines:SizeMismatch','Mask and lineIds must have the same length.');
end
if isempty(lineIds)
    lineMask = false(totalLines,1);
    return
end
if any(diff(lineIds) <= 0) || lineIds(1) < 1 || lineIds(end) > totalLines
    error('expandMotionMaskToLines:InvalidLineIds','lineIds must increase within [1,%d].',totalLines);
end
counts = diff([lineIds; totalLines+1]);
counts(1) = counts(1) + (lineIds(1)-1);
lineMask = repelem(maskSamples, counts);
if numel(lineMask) ~= totalLines
    error('expandMotionMaskToLines:LengthMismatch', ...
        'Expanded mask has %d lines but the source has %d.',numel(lineMask),totalLines);
end
end
