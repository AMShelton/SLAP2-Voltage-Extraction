function setup()
%SETUP Add SLAP2 Voltage Extraction to the MATLAB path and verify dependencies.
root = fileparts(mfilename('fullpath'));
addpath(root,'-begin');
addpath(fullfile(root,'source_extraction'),'-begin');
addpath(fullfile(root,'dependencies','io'),'-begin');
addpath(fullfile(root,'dependencies','gui'),'-begin');
addpath(fullfile(root,'dependencies','slap2_trace'),'-begin');
addpath(fullfile(root,'presets'),'-begin');

% The binary reader remains external, but the voltage Trace/TracePixel kernel
% is pinned in this repository for reproducibility and MATLAB->Python parity.
externalRequired = { ...
    'slap2.Slap2DataFile', ...
    'slap2.util.MultiDataFiles'};
missingExternal = {};
for k = 1:numel(externalRequired)
    if isempty(which(externalRequired{k}))
        missingExternal{end+1} = externalRequired{k}; %#ok<AGROW>
    end
end
if ~isempty(missingExternal)
    warning('Voltage:MissingSLAP2Dependency', ...
        'Missing external SLAP2 classes: %s', strjoin(missingExternal,', '));
end

vendoredRequired = { ...
    'slap2.util.datafile.trace.Trace', ...
    'slap2.util.datafile.trace.TracePixel'};
for k = 1:numel(vendoredRequired)
    resolved = which(vendoredRequired{k});
    if isempty(resolved)
        error('Voltage:MissingVendoredTraceKernel', ...
            'Vendored class %s did not resolve after setup.', vendoredRequired{k});
    end
end

fprintf('SLAP2 Voltage Extraction paths configured.\n');
fprintf('  Trace:      %s\n', which('slap2.util.datafile.trace.Trace'));
fprintf('  TracePixel: %s\n', which('slap2.util.datafile.trace.TracePixel'));
end
