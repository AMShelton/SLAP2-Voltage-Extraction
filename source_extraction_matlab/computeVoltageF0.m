function [f0, meta] = computeVoltageF0(rawF, sampleRateHz, params)
%COMPUTEVOLTAGEF0 Compute the voltage F0 model used for dF/F.
%
% The robust method mirrors vip-slap2-analysis:
%   1. bin the trace in time;
%   2. estimate a percentile in each bin;
%   3. apply a centered moving median to the bin estimates;
%   4. linearly interpolate the slow baseline back to native sampling.
%
% rawF is one ROI trace. F0 is returned with the same orientation as rawF.

if nargin < 3 || isempty(params)
    params = setParams('Voltage', struct());
end

wasRow = isrow(rawF);
raw = single(rawF(:));
if isempty(raw)
    f0 = cast(rawF, params.precision);
    meta = struct('method', params.f0Method, 'sampleRateHz', sampleRateHz);
    return
end
validateattributes(sampleRateHz, {'numeric'}, {'scalar','real','finite','positive'});

switch lower(char(params.f0Method))
    case 'static'
        baseline = robustPercentile(raw, params.f0Percentile);
        baseline = safeBaselineScalar(baseline, raw);
        f0Single = repmat(single(baseline), size(raw));
        meta = struct( ...
            'method', 'static_percentile', ...
            'percentile', double(params.f0Percentile), ...
            'sampleRateHz', double(sampleRateHz), ...
            'timeVarying', false);

    case 'robust'
        binSamples = max(1, round(double(params.f0Bin_s) * double(sampleRateHz)));
        nBins = ceil(numel(raw) / binSamples);
        if nBins <= 1
            baseline = robustPercentile(raw, params.f0Percentile);
            baseline = safeBaselineScalar(baseline, raw);
            f0Single = repmat(single(baseline), size(raw));
            meta = struct( ...
                'method', 'static_percentile', ...
                'percentile', double(params.f0Percentile), ...
                'sampleRateHz', double(sampleRateHz), ...
                'timeVarying', false);
        else
            binCenters = zeros(nBins,1);
            binF0 = nan(nBins,1,'single');
            for b = 1:nBins
                first = (b-1)*binSamples + 1;
                last = min(numel(raw), b*binSamples);
                binCenters(b) = ((first-1) + (last-1)) / 2;
                binF0(b) = single(robustPercentile(raw(first:last), params.f0Percentile));
            end

            smoothBins = max(1, round(double(params.f0Smooth_s) / double(params.f0Bin_s)));
            if mod(smoothBins,2) == 0
                smoothBins = smoothBins + 1;
            end

            fallback = median(abs(raw), 'omitnan');
            if ~isfinite(fallback) || fallback <= eps('single')
                fallback = single(1);
            end
            filled = fillNanLikeNumpy(binF0, fallback);
            smoothBinsF0 = centeredMovingMedian(filled, smoothBins);
            smoothBinsF0 = fillNanLikeNumpy(smoothBinsF0, fallback);

            sampleIdx = (0:numel(raw)-1)';
            interpF0 = interp1(binCenters, double(smoothBinsF0), double(sampleIdx), 'linear', NaN);
            interpF0(sampleIdx < binCenters(1)) = double(smoothBinsF0(1));
            interpF0(sampleIdx > binCenters(end)) = double(smoothBinsF0(end));
            f0Single = safeBaselineVector(single(interpF0), raw);

            meta = struct( ...
                'method', 'robust_binned_percentile_moving_median', ...
                'percentile', double(params.f0Percentile), ...
                'bin_s', double(params.f0Bin_s), ...
                'smooth_s', double(params.f0Smooth_s), ...
                'bin_samples', double(binSamples), ...
                'smooth_bins', double(smoothBins), ...
                'n_bins', double(nBins), ...
                'sampleRateHz', double(sampleRateHz), ...
                'timeVarying', true);
        end

    otherwise
        error('computeVoltageF0:UnknownMethod', 'Unknown F0 method: %s', params.f0Method);
end

if strcmpi(params.precision,'double')
    f0 = double(f0Single);
else
    f0 = single(f0Single);
end
if wasRow
    f0 = f0.';
end
end


function q = robustPercentile(x, percentile)
x = double(x(:));
x = x(isfinite(x));
if isempty(x)
    q = NaN;
else
    q = prctile(x, double(percentile));
end
end


function baseline = safeBaselineScalar(baseline, raw)
fallback = median(abs(raw), 'omitnan');
if ~isfinite(fallback) || fallback <= eps('single')
    fallback = single(1);
end
if ~isfinite(baseline) || abs(baseline) <= eps('single')
    baseline = fallback;
end
baseline = single(baseline);
end


function f0 = safeBaselineVector(f0, raw)
fallback = median(abs(raw), 'omitnan');
if ~isfinite(fallback) || fallback <= eps('single')
    fallback = single(1);
end
bad = ~isfinite(f0) | abs(f0) <= eps('single');
f0(bad) = single(fallback);
end


function out = fillNanLikeNumpy(x, fallback)
% Match numpy.interp behavior used by vip-slap2-analysis: linear fill between
% valid bins and constant endpoint extension outside the valid range.
x = single(x(:));
out = x;
valid = isfinite(x);
if all(valid)
    return
end
if ~any(valid)
    out(:) = single(fallback);
    return
end
idx = (1:numel(x))';
validIdx = idx(valid);
validVal = double(x(valid));
missing = ~valid;
inside = missing & idx >= validIdx(1) & idx <= validIdx(end);
if any(inside)
    out(inside) = single(interp1(double(validIdx), validVal, double(idx(inside)), 'linear'));
end
out(missing & idx < validIdx(1)) = x(validIdx(1));
out(missing & idx > validIdx(end)) = x(validIdx(end));
end


function out = centeredMovingMedian(x, windowBins)
x = single(x(:));
windowBins = max(1, round(windowBins));
if mod(windowBins,2)==0
    windowBins = windowBins + 1;
end
if windowBins <= 1
    out = x;
    return
end
half = floor(windowBins/2);
out = nan(size(x),'single');
for i = 1:numel(x)
    lo = max(1, i-half);
    hi = min(numel(x), i+half);
    out(i) = single(median(x(lo:hi), 'omitnan'));
end
end
