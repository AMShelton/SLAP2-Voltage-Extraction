function motion = readSourceOnlineMotion(hMDF, samplesPerCycle, lineRateHz)
%READSOURCEONLINEMOTION Read online xy/z motion offsets from SLAP2 line headers.
%
%   motion = readSourceOnlineMotion(hMDF, samplesPerCycle, lineRateHz)
%
% hMDF            slap2.util.MultiDataFiles for one acquisition source.
% samplesPerCycle Lines read per SLAP2 cycle, evenly spaced (default 1).
% lineRateHz      SLAP2 line rate (Hz).
%
% Offsets come from getOnlineMotion (vendored from GIAnT). The returned struct
% has x/y (pixels), z (um), the global line ids they were read at, the
% uniform sampling rate of the offset series, and the file geometry.

if nargin < 2 || isempty(samplesPerCycle), samplesPerCycle = 1; end
validateattributes(samplesPerCycle,{'numeric'},{'scalar','integer','positive','finite'});
validateattributes(lineRateHz,{'numeric'},{'scalar','real','finite','positive'});

lpc = numel(hMDF.lineHeaderIdxs);
nCycles = double(hMDF.numCycles);
s = min(samplesPerCycle, lpc);

res = unique(floor(((0:s-1)*lpc)/s) + 1);
lineIds = reshape(res(:) + (0:nCycles-1)*lpc, [], 1);

[x,y,z] = getOnlineMotion(hMDF, lineIds);

motion = struct();
motion.x = x(:);
motion.y = y(:);
motion.z = z(:);
motion.lineIds = lineIds;
motion.fsOffsets = lineRateHz / lpc * numel(res);
motion.linesPerCycle = lpc;
motion.numCycles = nCycles;
motion.totalLines = lpc*nCycles;
motion.lineRateHz = lineRateHz;
motion.sampleTimes_s = (lineIds-1)/lineRateHz;
end
