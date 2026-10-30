function [mask, info] = computeMotionCensor(xOffset_pix, yOffset_pix, fsHz, params)
%COMPUTEMOTIONCENSOR Flag motion-contaminated samples from online xy offsets.
%
%   [mask, info] = computeMotionCensor(x_pix, y_pix, fsHz, params)
%
% x_pix, y_pix  Online motion-correction offsets (pixels), uniformly sampled
%               at fsHz. Non-finite offsets are censored.
% params        Struct with the motion* fields from motionCensorDefaults.
%
% Rule (mirrors GIAnT loadAndProcessTrialAsync.m, applied to |xy| in um):
%   1. m   = pixel_um * hypot(x, y)
%   2. dev = m - running median of m (motionMedianWindow_s)
%   3. nd  = dev / max(|5th percentile of dev|, motionScaleFloor_um)
%   4. flag = nd > motionThresh
%   5. flag = dilate(flag, +/-motionPad_s) & (nd > motionThresh/2), so padding
%      only reaches shoulder samples above half the threshold; then close
%      gaps shorter than motionMergeGap_s
%   6. also flag m > motionAbsMax_um when that cap is > 0
%   7. flag the first motionDiscardInitial_s seconds
%
% Returns mask (logical column, true = censor) and an info struct with the
% intermediate traces for plotting/QC.

validateattributes(fsHz,{'numeric'},{'scalar','real','finite','positive'});
params = validateMotionCensorParams(params);
x = double(xOffset_pix(:));
y = double(yOffset_pix(:));
if numel(x) ~= numel(y)
    error('computeMotionCensor:SizeMismatch','x and y offsets must have the same length.');
end
n = numel(x);

bad = ~isfinite(x) | ~isfinite(y);
m = params.motionPixelSize_um * hypot(x,y);
m(bad) = NaN;

if n == 0
    mask = false(0,1);
    info = emptyInfo(m,params,fsHz);
    return
end

win = oddWindow(params.motionMedianWindow_s*fsHz, n);
base = movmedian(m,win,'omitnan');
dev = m - base;

lowerTail = prctile(dev(isfinite(dev)),5);
if isempty(lowerTail) || ~isfinite(lowerTail), lowerTail = 0; end
scale = max(abs(lowerTail), params.motionScaleFloor_um);
nd = dev ./ scale;

flag = nd > params.motionThresh;
padN = ceil(params.motionPad_s*fsHz);
if padN > 0
    flagPad = movmax(double(flag), 2*padN+1) > 0;
else
    flagPad = flag;
end
cand = flagPad & (nd > params.motionThresh/2);
gapN = ceil(params.motionMergeGap_s*fsHz);
if gapN > 0
    closeWin = 2*gapN+1;
    cand = movmin(movmax(double(cand),closeWin),closeWin) > 0;
end
mask = cand;

if params.motionAbsMax_um > 0
    mask = mask | (m > params.motionAbsMax_um);
end
mask = mask | bad;

nInit = min(n, ceil(params.motionDiscardInitial_s*fsHz));
if nInit > 0
    mask(1:nInit) = true;
end
mask = logical(mask(:));

info = struct();
info.fsHz = fsHz;
info.magnitude_um = m;
info.baseline_um = base;
info.deviation_um = dev;
info.normalizedDeviation = nd;
info.scale_um = scale;
info.lowerTail_um = lowerTail;
info.medianWindowSamples = win;
info.threshold_um = params.motionThresh*scale;
info.fractionCensored = mean(mask);
end


function win = oddWindow(w, n)
win = max(1, round(w));
if mod(win,2) == 0, win = win + 1; end
win = min(win, 2*floor((n-1)/2)+1);
win = max(win,1);
end


function info = emptyInfo(m,params,fsHz)
info = struct('fsHz',fsHz,'magnitude_um',m,'baseline_um',m,'deviation_um',m, ...
    'normalizedDeviation',m,'scale_um',params.motionScaleFloor_um,'lowerTail_um',0, ...
    'medianWindowSamples',1,'threshold_um',params.motionThresh*params.motionScaleFloor_um, ...
    'fractionCensored',0);
end
