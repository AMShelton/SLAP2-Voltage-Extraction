function [lineMask, info] = computeSourceMotionMask(hMDF, params, lineRateHz)
%COMPUTESOURCEMOTIONMASK Line-resolution motion-censor mask for one SLAP2 source.
%
%   [lineMask, info] = computeSourceMotionMask(hMDF, params, lineRateHz)
%
% hMDF       slap2.util.MultiDataFiles for one acquisition source.
% params     Parameters from motionCensorDefaults (validated here).
% lineRateHz SLAP2 line rate (the output sampling rate of the trace).
%
% Reads the online offsets (readSourceOnlineMotion), censors them
% (computeMotionCensor), then expands to one logical value per SLAP2 line with
% a zero-order hold, because the offsets are held between header updates.
% lineMask(i) indexes the same global line axis as the Trace output and the
% trial table first_line/last_line.

params = validateMotionCensorParams(params);
motion = readSourceOnlineMotion(hMDF, params.motionSamplesPerCycle, lineRateHz);

[maskS, info] = computeMotionCensor(motion.x, motion.y, motion.fsOffsets, params);
lineMask = expandMotionMaskToLines(maskS, motion.lineIds, motion.totalLines);

info.lineIds = motion.lineIds;
info.xOffset_pix = motion.x;
info.yOffset_pix = motion.y;
info.zOffset_um = motion.z;
info.linesPerCycle = motion.linesPerCycle;
info.numCycles = motion.numCycles;
info.totalLines = motion.totalLines;
info.sampleTimes_s = motion.sampleTimes_s;
end
