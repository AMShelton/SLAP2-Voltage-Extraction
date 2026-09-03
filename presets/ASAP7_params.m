function params = ASAP7_params(varargin)
%ASAP7_PARAMS Voltage parameters for ASAP7-family quenched indicators.
overrides = struct('indicatorName','ASAP7','indicatorDirection','decreases');
if nargin>0 && ~isempty(varargin{1})
    user = varargin{1};
    for f = fieldnames(user)'
        overrides.(f{1}) = user.(f{1});
    end
end
params = setParams('Voltage',overrides);
end
