function [dff, meta] = computeVoltageDFF(rawF, f0, indicatorName, indicatorDirection, precision)
%COMPUTEVOLTAGEDFF Compute polarity-corrected voltage dF/F.
%
% The sign convention matches vip-slap2-analysis: positive dff represents a
% positive membrane-voltage deflection. ASAP7-like indicators therefore use
% (F0-F)/F0, while ASAP8-like indicators use (F-F0)/F0.

if nargin < 3 || isempty(indicatorName), indicatorName = ''; end
if nargin < 4 || isempty(indicatorDirection), indicatorDirection = 'auto'; end
if nargin < 5 || isempty(precision), precision = 'single'; end

[signValue, resolvedDirection, source] = resolveDirection(indicatorName, indicatorDirection);
raw = single(rawF);
baseline = single(f0);
if ~isequal(size(raw),size(baseline))
    error('computeVoltageDFF:SizeMismatch', 'rawF and f0 must have identical size.');
end

fallback = median(abs(raw(:)), 'omitnan');
if ~isfinite(fallback) || fallback <= eps('single')
    fallback = single(1);
end
bad = ~isfinite(baseline) | abs(baseline) <= eps('single');
baseline(bad) = single(fallback);

dffSingle = single(signValue) .* (raw - baseline) ./ baseline;
if strcmpi(precision,'double')
    dff = double(dffSingle);
else
    dff = dffSingle;
end

if signValue > 0
    formula = 'dff = (F - F0) / F0';
else
    formula = 'dff = (F0 - F) / F0';
end
meta = struct( ...
    'indicatorName', char(string(indicatorName)), ...
    'indicatorDirectionRequested', char(string(indicatorDirection)), ...
    'indicatorDirectionResolved', resolvedDirection, ...
    'directionSource', source, ...
    'dffSign', double(signValue), ...
    'formula', formula);
end


function [signValue, resolved, source] = resolveDirection(indicatorName, requested)
requested = lower(strrep(strrep(strtrim(char(string(requested))),'-','_'),' ','_'));
indicator = lower(strtrim(char(string(indicatorName))));

switch requested
    case {'increases','increase','standard','positive','brightens'}
        signValue = 1;
        resolved = 'increases';
        source = 'explicit';
    case {'decreases','decrease','inverted','negative','quenched','quenching'}
        signValue = -1;
        resolved = 'decreases';
        source = 'explicit';
    case 'auto'
        if contains(indicator,'asap8')
            signValue = 1;
            resolved = 'increases';
            source = 'indicatorName';
        elseif contains(indicator,'asap7')
            signValue = -1;
            resolved = 'decreases';
            source = 'indicatorName';
        else
            error('computeVoltageDFF:UnknownIndicatorDirection', ...
                ['indicatorDirection="auto" requires indicatorName to identify the fluorescence polarity. ' ...
                 'Set indicatorName to ASAP7/ASAP8 or set indicatorDirection explicitly.']);
        end
    otherwise
        error('computeVoltageDFF:InvalidDirection', ...
            'indicatorDirection must be auto, increases, or decreases.');
end
end
