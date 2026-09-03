function setup()
%SETUP Add SLAP2 Voltage Extraction to the MATLAB path and verify dependencies.
root = fileparts(mfilename('fullpath'));
addpath(root);
addpath(fullfile(root,'source_extraction'));
addpath(fullfile(root,'dependencies','io'));
addpath(fullfile(root,'dependencies','gui'));
addpath(fullfile(root,'presets'));

required = { ...
    'slap2.Slap2DataFile', ...
    'slap2.util.MultiDataFiles', ...
    'slap2.util.datafile.trace.Trace'};
missing = {};
for k = 1:numel(required)
    if isempty(which(required{k}))
        missing{end+1} = required{k}; %#ok<AGROW>
    end
end
if ~isempty(missing)
    warning('Voltage:MissingSLAP2Dependency', ...
        'Missing external SLAP2 classes: %s', strjoin(missing,', '));
else
    fprintf('SLAP2 Voltage Extraction paths configured.\n');
end
end
