function params = ASAP8_params(varargin)
%ASAP8_PARAMS Voltage parameters for ASAP8-family brightening indicators.
overrides = struct('indicatorName','ASAP8','indicatorDirection','increases');
if nargin>0 && ~isempty(varargin{1})
    user = varargin{1};
    for f = fieldnames(user)'
        overrides.(f{1}) = user.(f{1});
    end
end
params = setParams('Voltage',overrides);
end
