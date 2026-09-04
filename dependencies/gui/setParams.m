function params = setParams(fnName, paramsIn, forceGUI)
%SETPARAMS Parameters for SLAP2 voltage extraction.
%
%   params = setParams('Voltage') opens the parameter GUI.
%   params = setParams('Voltage', paramsIn) merges a struct without opening it.

if nargin < 1 || isempty(fnName)
    fnName = 'Voltage';
end

switch char(fnName)
    case 'Voltage'
        params = struct();
        tooltips = struct();

        % SLAP2 Trace extraction parameters. These define raw fluorescence F.
        params.chIdx = 1;
        tooltips.chIdx = 'Channel index passed to slap2.util.datafile.trace.Trace.';

        params.zIdx = 1;
        tooltips.zIdx = 'Z-plane index passed to Trace. Usually 1 for single-plane voltage recordings.';

        params.traceWindow_lines = 16;
        tooltips.traceWindow_lines = 'Temporal weighting window (SLAP2 lines) passed to Trace.process.';

        params.traceExpectedWindow_lines = 5000;
        tooltips.traceExpectedWindow_lines = 'Expected-fluorescence window (SLAP2 lines) passed to Trace.process.';

        % Voltage dF/F parameters. Defaults reproduce the robust-F0 pathway used
        % in vip-slap2-analysis; F0 is fit independently within acquisition epochs.
        params.indicatorName = '';
        tooltips.indicatorName = 'Indicator name (for example ASAP7y or ASAP8). Used when indicatorDirection=auto.';

        params.indicatorDirection = 'auto';
        tooltips.indicatorDirection = ['Fluorescence response to depolarization: auto infers ASAP7/ASAP8 from indicatorName; ' ...
            'increases uses (F-F0)/F0; decreases uses (F0-F)/F0.'];
        tooltips.choiceLists.indicatorDirection = {'auto','increases','decreases'};

        params.f0Method = 'robust';
        tooltips.f0Method = 'F0 model: robust binned percentile + moving median, or static session percentile.';
        tooltips.choiceLists.f0Method = {'robust','static'};

        params.f0Percentile = 50;
        tooltips.f0Percentile = 'Percentile used to estimate baseline fluorescence within each F0 bin.';

        params.f0Bin_s = 5;
        tooltips.f0Bin_s = 'Robust F0 bin duration in seconds.';

        params.f0Smooth_s = 180;
        tooltips.f0Smooth_s = 'Centered moving-median duration applied to robust F0 bin estimates, in seconds.';

        % Runtime / output parameters.
        params.useParallel = true;
        tooltips.useParallel = 'Use asynchronous SLAP2 Trace extraction when a parallel pool is available.';

        params.nWorkers = 4;
        tooltips.nWorkers = 'Requested MATLAB process workers for voltage extraction.';

        params.maxConcurrentROIs = 2;
        tooltips.maxConcurrentROIs = 'Maximum ROI traces launched concurrently. Primary memory/I/O throttle.';

        params.precision = 'single';
        tooltips.precision = 'Saved raw_f, f0, and dff precision.';
        tooltips.choiceLists.precision = {'single','double'};

        params.outputDir = '';
        tooltips.outputDir = 'Output directory. Empty creates a Voltage subfolder beside trial_table.h5.';

        params.outputFilename = 'VoltageSummary.h5';
        tooltips.outputFilename = 'Name of the SILo-like voltage summary HDF5 file.';

        params.overwrite = false;
        tooltips.overwrite = 'Overwrite an existing VoltageSummary.h5.';

        params.h5ChunkSamples = 100000;
        tooltips.h5ChunkSamples = 'HDF5 chunk length along the time/sample dimension.';

        params.h5Deflate = 0;
        tooltips.h5Deflate = 'HDF5 compression level (0-9). Zero is fastest and preferred for parity testing.';

    otherwise
        error('setParams:UnknownFunction', 'Unknown function name: %s', char(fnName));
end

if nargin > 1 && ~isempty(paramsIn)
    paramsIn = normalizeInput(paramsIn);
    fields = fieldnames(paramsIn);
    for k = 1:numel(fields)
        params.(fields{k}) = paramsIn.(fields{k});
    end
    params = validateVoltageParams(params);
    if nargin < 3 || ~forceGUI
        return
    end
else
    params = validateVoltageParams(params);
end

params = optionsGUI(params, tooltips, 'Voltage');
params = validateVoltageParams(params);
end


function params = validateVoltageParams(params)
validateattributes(params.chIdx, {'numeric'}, {'scalar','integer','positive','finite'});
validateattributes(params.zIdx, {'numeric'}, {'scalar','integer','positive','finite'});
validateattributes(params.traceWindow_lines, {'numeric'}, {'scalar','integer','positive','finite'});
validateattributes(params.traceExpectedWindow_lines, {'numeric'}, {'scalar','integer','positive','finite'});
validateattributes(params.f0Percentile, {'numeric'}, {'scalar','real','finite','>=',0,'<=',100});
validateattributes(params.f0Bin_s, {'numeric'}, {'scalar','real','finite','positive'});
validateattributes(params.f0Smooth_s, {'numeric'}, {'scalar','real','finite','positive'});
validateattributes(params.nWorkers, {'numeric'}, {'scalar','real','finite','positive'});
validateattributes(params.maxConcurrentROIs, {'numeric'}, {'scalar','real','finite','positive'});
validateattributes(params.h5ChunkSamples, {'numeric'}, {'scalar','real','finite','positive'});
validateattributes(params.h5Deflate, {'numeric'}, {'scalar','real','finite','>=',0,'<=',9});

params.nWorkers = max(1, round(double(params.nWorkers)));
params.maxConcurrentROIs = max(1, round(double(params.maxConcurrentROIs)));
params.h5ChunkSamples = max(1, round(double(params.h5ChunkSamples)));
params.h5Deflate = round(double(params.h5Deflate));
params.useParallel = logicalScalar(params.useParallel, 'useParallel');
params.overwrite = logicalScalar(params.overwrite, 'overwrite');

params.indicatorName = char(string(params.indicatorName));
params.indicatorDirection = validatestring(char(params.indicatorDirection), {'auto','increases','decreases'});
params.f0Method = validatestring(char(params.f0Method), {'robust','static'});
params.precision = validatestring(char(params.precision), {'single','double'});
params.outputDir = char(string(params.outputDir));
params.outputFilename = char(string(params.outputFilename));
if isempty(strtrim(params.outputFilename))
    error('setParams:InvalidOutputFilename', 'outputFilename cannot be empty.');
end
end


function paramsIn = normalizeInput(paramsIn)
if isstruct(paramsIn)
    return
end
if ischar(paramsIn) || (isstring(paramsIn) && isscalar(paramsIn))
    txt = char(paramsIn);
    if exist(txt, 'file') == 2
        [~,~,ext] = fileparts(txt);
        if strcmpi(ext,'.mat')
            S = load(txt);
            if isfield(S,'optsOut')
                paramsIn = S.optsOut;
            elseif isfield(S,'params')
                paramsIn = S.params;
            else
                names = fieldnames(S);
                if numel(names)==1 && isstruct(S.(names{1}))
                    paramsIn = S.(names{1});
                else
                    error('setParams:InvalidPreset', 'MAT preset must contain optsOut, params, or one struct variable.');
                end
            end
        else
            paramsIn = jsondecode(fileread(txt));
        end
    else
        paramsIn = jsondecode(txt);
    end
else
    error('setParams:InvalidInput', 'paramsIn must be a struct, JSON string/file, or MAT preset.');
end
if ~isstruct(paramsIn) || ~isscalar(paramsIn)
    error('setParams:InvalidInput', 'Resolved paramsIn must be a scalar struct.');
end
end


function out = logicalScalar(value, name)
if islogical(value) && isscalar(value)
    out = value;
elseif isnumeric(value) && isscalar(value) && isfinite(value) && any(value == [0 1])
    out = logical(value);
else
    error('setParams:InvalidLogical', '%s must be a scalar logical or 0/1.', name);
end
end
