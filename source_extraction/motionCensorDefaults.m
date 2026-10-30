function [params, tooltips] = motionCensorDefaults()
%MOTIONCENSORDEFAULTS Default motion-censoring parameters and GUI tooltips.
%
% Single source of truth for every motion* parameter. Both setParams.m
% (Voltage.m path) and processVoltage.m (localVoltageParams) merge this struct
% so the two parameter paths cannot drift apart.
%
% The rule mirrors GIAnT's glutamate frame censoring
% (loadAndProcessTrialAsync.m), but applies it to the microscope's online
% motion-correction offsets because integration-mode voltage has no images
% and therefore no registration error (recNegErr):
%
%   m   = motionPixelSize_um * hypot(xOffset_pix, yOffset_pix)
%   dev = m - movmedian(m, motionMedianWindow_s)
%   nd  = dev / max(abs(prctile(dev,5)), motionScaleFloor_um)
%   censor where nd > motionThresh  (padded, gap-merged), or m > motionAbsMax_um

params = struct();
tooltips = struct();

params.motionCensorEnable = false;
tooltips.motionCensorEnable = ['Censor motion-contaminated samples. dff and f0 are set to NaN where censored; ' ...
    'raw_f is left intact and the mask is saved in frame_info/motion_censor.'];

params.motionPixelSize_um = 0.25;
tooltips.motionPixelSize_um = 'SLAP2 pixel size (um/pixel) used to convert online xy offsets to microns.';

params.motionMedianWindow_s = 4;
tooltips.motionMedianWindow_s = ['Running-median window (s) removing slow drift from the xy offset magnitude. ' ...
    'GIAnT uses 4 s.'];

params.motionThresh = 2.5;
tooltips.motionThresh = ['Censor when the drift-removed xy offset exceeds this many units of the robust scale ' ...
    '(GIAnT motionThresh semantics). Decrease to be more stringent.'];

params.motionScaleFloor_um = 0.25;
tooltips.motionScaleFloor_um = ['Minimum robust scale (um). Online offsets are integer pixels, so the lower-tail ' ...
    'spread can be zero; the floor (default one pixel) keeps the threshold finite.'];

params.motionAbsMax_um = 0;
tooltips.motionAbsMax_um = ['Optional hard cap (um) on the raw xy offset magnitude, applied in addition to the ' ...
    'drift-removed rule. 0 disables.'];

params.motionPad_s = 0.025;
tooltips.motionPad_s = ['Extend each censored span by up to this many seconds on both sides, but only into samples above ' ...
    'motionThresh/2 (GIAnT uses 25 ms).'];

params.motionMergeGap_s = 0.05;
tooltips.motionMergeGap_s = 'Merge censored spans separated by less than this many seconds.';

params.motionDiscardInitial_s = 0;
tooltips.motionDiscardInitial_s = 'Always censor this many seconds at the start of each source file (warm-up).';

params.motionSamplesPerCycle = 1;
tooltips.motionSamplesPerCycle = ['Online offsets read per SLAP2 cycle (evenly spaced lines). Offsets can change ' ...
    'within a cycle; increase to resolve that at the cost of header reads.'];

params.motionMaxFracCensored = 0.25;
tooltips.motionMaxFracCensored = 'Warn when more than this fraction of a source file is censored.';
end
