function params = validateMotionCensorParams(params)
%VALIDATEMOTIONCENSORPARAMS Validate and normalize motion-censoring parameters.
%
% Missing fields are filled from motionCensorDefaults so older presets keep
% working.

defaults = motionCensorDefaults();
names = fieldnames(defaults);
for k = 1:numel(names)
    if ~isfield(params,names{k})
        params.(names{k}) = defaults.(names{k});
    end
end

params.motionCensorEnable = localLogical(params.motionCensorEnable,'motionCensorEnable');
pos = {'motionPixelSize_um','motionMedianWindow_s','motionThresh','motionScaleFloor_um'};
for k = 1:numel(pos)
    validateattributes(params.(pos{k}),{'numeric'},{'scalar','real','finite','positive'},mfilename,pos{k});
end
nonneg = {'motionAbsMax_um','motionPad_s','motionMergeGap_s','motionDiscardInitial_s'};
for k = 1:numel(nonneg)
    validateattributes(params.(nonneg{k}),{'numeric'},{'scalar','real','finite','nonnegative'},mfilename,nonneg{k});
end
validateattributes(params.motionSamplesPerCycle,{'numeric'},{'scalar','integer','positive','finite'},mfilename,'motionSamplesPerCycle');
validateattributes(params.motionMaxFracCensored,{'numeric'},{'scalar','real','finite','>',0,'<=',1},mfilename,'motionMaxFracCensored');
end


function out = localLogical(value,name)
if islogical(value) && isscalar(value)
    out = value;
elseif isnumeric(value) && isscalar(value) && isfinite(value)
    out = value ~= 0;
else
    error('validateMotionCensorParams:InvalidLogical','%s must be a logical scalar.',name);
end
end
