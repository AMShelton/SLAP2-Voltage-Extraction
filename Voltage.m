function summary = Voltage(dr_or_pathToTrialTable, paramsIn)
%VOLTAGE Extract SLAP2 integration-ROI voltage fluorescence to VoltageSummary.h5.
%
%   summary = Voltage(pathToTrialTableH5)
%   summary = Voltage(pathToTrialTableH5, params)
%
% Input
%   GIAnT-compatible trial_table.h5 produced by buildTrialTableSLAP2.m.
%
% Output
%   VoltageSummary.h5 with a SILo-like per-Path hierarchy:
%       /params
%       /Path#/Z_depths
%       /Path#/sample_rate_hz
%       /Path#/frame_info/{trial_num_frames,trial_epoch,frame_line_idxs,sample_epoch}
%       /Path#/sources/spatial/{profiles,coords,source_roi_index,roi_pixel_count}
%       /Path#/sources/temporal/{raw_f,f0,dff}
%
% raw_f is the direct SLAP2 Trace output. F0 and dff are calculated from the
% in-memory raw trace whenever one source file contains a complete acquisition
% epoch. This is the normal fast path for continuous CYCLE recordings and avoids
% rereading raw_f from HDF5. A bounded HDF5 fallback is retained only for epochs
% assembled from multiple raw source files. No motion correction is performed.

bootstrapRepositoryPaths();
runTimer = tic;

if nargin < 1 || isempty(dr_or_pathToTrialTable)
    [fn, dr] = uigetfile({'*.h5','HDF5 files (*.h5)'}, 'Select trial_table.h5');
    assert(~isnumeric(fn), 'No trial table selected.');
    trialTablePath = fullfile(dr, fn);
else
    trialTablePath = resolveTrialTablePath(dr_or_pathToTrialTable);
end

if nargin < 2
    params = setParams('Voltage');
else
    params = setParams('Voltage', paramsIn);
end

trialTable = loadStructFromH5(trialTablePath);
validateTrialTable(trialTable);
trialTableDir = fileparts(trialTablePath);
dataDir = resolveDataDir(trialTable, trialTableDir);

if isempty(params.outputDir)
    outputDir = fullfile(trialTableDir, 'Voltage');
else
    outputDir = params.outputDir;
end
if ~exist(outputDir,'dir')
    mkdir(outputDir);
end
outputPath = fullfile(outputDir, params.outputFilename);
if exist(outputPath,'file')
    if params.overwrite
        delete(outputPath);
    else
        error('Voltage:OutputExists', ...
            'Output already exists: %s. Set params.overwrite=true to replace it.', outputPath);
    end
end

filename = normalizeFilenameGrid(trialTable.filename);
firstLineRaw = double(trialTable.slap2_info.first_line);
lastLineRaw = double(trialTable.slap2_info.last_line);
nPaths = size(filename,1);
nTrials = size(filename,2);
if ~isequal(size(firstLineRaw),size(filename)) || ~isequal(size(lastLineRaw),size(filename))
    error('Voltage:TrialTableShapeMismatch', ...
        'filename, slap2_info.first_line, and slap2_info.last_line must have identical size.');
end
[firstLine,lastLine] = normalizeLineRanges(trialTable,filename,firstLineRaw,lastLineRaw);

analysisEpoch = inferAnalysisEpochs(trialTable, filename);
trialNumSamples = zeros(nPaths,nTrials);
for p = 1:nPaths
    for t = 1:nTrials
        if isempty(filename{p,t}), continue, end
        a = firstLine(p,t);
        b = lastLine(p,t);
        if isfinite(a) && isfinite(b) && a >= 1 && b >= a
            trialNumSamples(p,t) = b-a+1;
        end
    end
end

try
rootPayload = struct();
rootPayload.format_version = '0.2.3';
rootPayload.params = params;
saveStructToH5(rootPayload, outputPath);

summary = struct();
summary.trialTablePath = trialTablePath;
summary.outputPath = outputPath;
summary.params = params;
summary.nPaths = nPaths;
summary.nTrials = nTrials;
summary.path = repmat(struct(),1,nPaths);
summary.timing = struct();
summary.timing.path = repmat(emptyTiming(),1,nPaths);

% Start the process pool lazily only after at least one path has passed
% metadata/ROI discovery. This avoids paying pool-startup cost for invalid
% sessions (for example, a table whose raw sources contain no Voltage ROIs).
parallelConfigured = false;
totalVoltageRoisFound = 0;

for pathIdx = 1:nPaths
    pathTimer = tic;
    timing = emptyTiming();
    fprintf('\n=== Voltage Path%d/%d ===\n', pathIdx, nPaths);
    validTrials = find(~cellfun(@isempty, filename(pathIdx,:)) & trialNumSamples(pathIdx,:) > 0);
    if isempty(validTrials)
        warning('Voltage:NoValidTrials', 'Path%d has no valid trials; skipping.', pathIdx);
        timing.total_s = toc(pathTimer);
        summary.timing.path(pathIdx) = timing;
        continue
    end

    sourceFiles = filename(pathIdx,validTrials);
    [uniqueSources,~,sourceGroup] = unique(sourceFiles,'stable');

    % Open the first source once and keep it alive through its extraction pass.
    % The previous implementation opened this file for metadata, closed it, then
    % immediately reopened it for extraction.
    firstSource = resolveDataFilePath(dataDir, trialTableDir, uniqueSources{1});
    metadataTimer = tic;
    hFirstMDF = slap2.util.MultiDataFiles(firstSource);
    validateParsePlanCompatibility(hFirstMDF, pathIdx);
    [masks, sourceRoiIdx, roiDiscovery] = discoverVoltageROIs( ...
        hFirstMDF, params.zIdx, params.chIdx);
    sampleRateHz = resolveSampleRateHz(hFirstMDF);
    zDepth = resolveZDepth(hFirstMDF);
    canonicalMeta = getGeometryMeta(hFirstMDF);
    timing.metadata_s = timing.metadata_s + toc(metadataTimer);

    nRois = size(masks,3);
    totalVoltageRoisFound = totalVoltageRoisFound + nRois;
    fprintf('Path%d acquisition ROIs: %d; Voltage integration ROIs: %d', ...
        pathIdx, roiDiscovery.nAcquisitionROIs, nRois);
    if nRois > 0
        fprintf(' (source ROI indices %s)\n', mat2str(sourceRoiIdx));
    else
        fprintf('\n');
        for candidateIdx = 1:roiDiscovery.nAcquisitionROIs
            fprintf('  acquisition ROI %d: imagingMode=%s; integration TracePixels=%d\n', ...
                candidateIdx, roiDiscovery.imagingMode{candidateIdx}, ...
                roiDiscovery.integrationSuperPixelCounts(candidateIdx));
        end
        warning('Voltage:NoVoltageROIs', ...
            ['Path%d has no acquisition ROIs that map to integration-mode ' ...
             'samples in the SLAP2 parse plan; skipping source datasets.'], pathIdx);
    end

    [trialOffsets, totalSamples] = computeTrialOffsets(trialNumSamples(pathIdx,:));
    pathName = sprintf('/Path%d',pathIdx);

    summary.path(pathIdx).nAcquisitionROIs = roiDiscovery.nAcquisitionROIs;
    summary.path(pathIdx).nROIs = nRois;
    summary.path(pathIdx).sourceRoiIdx = sourceRoiIdx;
    summary.path(pathIdx).roiDiscovery = roiDiscovery;
    summary.path(pathIdx).sampleRateHz = sampleRateHz;
    summary.path(pathIdx).totalSamples = totalSamples;
    summary.path(pathIdx).trialNumSamples = trialNumSamples(pathIdx,:);
    summary.path(pathIdx).trialEpoch = analysisEpoch(pathIdx,:);

    if nRois == 0
        % Do not create per-sample HDF5 metadata for an empty path. On long
        % continuous sessions frame_line_idxs/sample_epoch can be hundreds of MB.
        delete(hFirstMDF); clear hFirstMDF
        timing.total_s = toc(pathTimer);
        summary.timing.path(pathIdx) = timing;
        summary.path(pathIdx).timing = timing;
        continue
    end

    outputInitTimer = tic;
    initializePathOutput(outputPath, pathName, masks, sourceRoiIdx, ...
        sampleRateHz, zDepth, trialNumSamples(pathIdx,:), analysisEpoch(pathIdx,:), ...
        firstLine(pathIdx,:), lastLine(pathIdx,:), trialOffsets, params);
    timing.output_init_s = timing.output_init_s + toc(outputInitTimer);

    if ~parallelConfigured
        params = configureParallelPool(params);
        summary.params = params;
        parallelConfigured = true;
    end

    % Identify epochs for which one raw source contains every valid trial. Those
    % epochs can be transformed directly from the in-memory Trace output. Only
    % multi-source epochs need the HDF5 fallback after extraction.
    allEpochIds = unique(analysisEpoch(pathIdx,validTrials),'stable');
    inMemoryEpochIds = [];
    for sourceIdx = 1:numel(uniqueSources)
        sourceTrials = validTrials(sourceGroup == sourceIdx);
        complete = completeEpochsForSource(sourceTrials, validTrials, analysisEpoch(pathIdx,:));
        inMemoryEpochIds = appendUniqueStable(inMemoryEpochIds, complete);
    end
    fallbackEpochIds = setdiff(allEpochIds, inMemoryEpochIds, 'stable');
    summary.path(pathIdx).inMemoryEpochIds = inMemoryEpochIds;
    summary.path(pathIdx).fallbackEpochIds = fallbackEpochIds;

    % Extract each distinct raw source file once. Continuous CYCLE pseudo-trials
    % usually point repeatedly to the same first CYCLE file, so this avoids
    % reprocessing the full acquisition for every pseudo-trial.
    for sourceIdx = 1:numel(uniqueSources)
        sourceName = uniqueSources{sourceIdx};
        sourceTrials = validTrials(sourceGroup == sourceIdx);
        sourcePath = resolveDataFilePath(dataDir, trialTableDir, sourceName);
        fprintf('Path%d source %d/%d: %s\n', pathIdx, sourceIdx, numel(uniqueSources), sourceName);

        if sourceIdx == 1
            hMDF = hFirstMDF;
            hFirstMDF = [];
            % Metadata/ROI discovery was already performed on this exact handle.
            sourceMasks = masks;
            sourceRoiIdxNow = sourceRoiIdx;
        else
            sourceOpenTimer = tic;
            hMDF = slap2.util.MultiDataFiles(sourcePath);
            timing.source_open_s = timing.source_open_s + toc(sourceOpenTimer);
            validateParsePlanCompatibility(hMDF, pathIdx);
            [sourceMasks, sourceRoiIdxNow] = discoverVoltageROIs( ...
                hMDF, params.zIdx, params.chIdx);
        end

        validateSourceCompatibility(pathIdx, sourceName, canonicalMeta, getGeometryMeta(hMDF), ...
            masks, sourceMasks, sourceRoiIdx, sourceRoiIdxNow, sampleRateHz, resolveSampleRateHz(hMDF));

        completeEpochIds = completeEpochsForSource(sourceTrials, validTrials, analysisEpoch(pathIdx,:));
        batches = makeBatches(1:nRois, params.maxConcurrentROIs);
        for batchIdx = 1:numel(batches)
            batch = batches{batchIdx};
            fprintf('  ROI batch %d/%d: %s\n', batchIdx, numel(batches), mat2str(batch));

            traceTimer = tic;
            [traces, errors] = extractRoiBatch(hMDF, masks, batch, params);
            timing.raw_trace_s = timing.raw_trace_s + toc(traceTimer);

            for j = 1:numel(batch)
                roiIdx = batch(j);
                if ~isempty(errors{j})
                    delete(hMDF);
                    error('Voltage:ROIExtractionFailed', ...
                        'Path%d ROI%d failed for %s:\n%s', pathIdx, roiIdx, sourceName, errors{j});
                end
                trace = castTrace(traces{j}, params.precision);
                traces{j} = []; % release the batch-held full trace before derived processing

                % Write raw fluorescence. For the normal CYCLE case, all pseudo-
                % trial slices are contiguous in both the source trace and output
                % axis, so this collapses dozens/hundreds of h5write calls to one.
                rawWriteTimer = tic;
                timing.raw_h5_writes = timing.raw_h5_writes + writeRawSourceSlices( ...
                    outputPath, pathName, trace, roiIdx, sourceTrials, ...
                    firstLine(pathIdx,:), lastLine(pathIdx,:), trialOffsets, ...
                    trialNumSamples(pathIdx,:));
                timing.raw_write_s = timing.raw_write_s + toc(rawWriteTimer);

                % Fast path: derive F0 and dF/F while raw F is still in memory.
                for epochId = reshape(completeEpochIds,1,[])
                    epochTrials = sourceTrials(analysisEpoch(pathIdx,sourceTrials) == epochId);
                    rawEpoch = concatenateTraceTrials(trace, epochTrials, ...
                        firstLine(pathIdx,:), lastLine(pathIdx,:), trialNumSamples(pathIdx,:));

                    derivedTimer = tic;
                    [f0,~] = computeVoltageF0(rawEpoch,sampleRateHz,params);
                    [dff,~] = computeVoltageDFF(rawEpoch,f0,params.indicatorName, ...
                        params.indicatorDirection,params.precision);
                    timing.derived_compute_s = timing.derived_compute_s + toc(derivedTimer);

                    derivedWriteTimer = tic;
                    writeDerivedEpoch(outputPath,pathName,roiIdx,epochTrials,trialOffsets, ...
                        trialNumSamples(pathIdx,:),f0,dff);
                    timing.derived_write_s = timing.derived_write_s + toc(derivedWriteTimer);
                    clear rawEpoch f0 dff
                end
                clear trace
            end
            clear traces errors
        end
        delete(hMDF); clear hMDF
    end

    % Fallback only for epochs assembled from multiple raw files. This preserves
    % epoch-scoped F0 semantics without penalizing the normal continuous-CYCLE path.
    if ~isempty(fallbackEpochIds)
        fprintf('Path%d: HDF5 fallback for multi-source epoch(s): %s\n', ...
            pathIdx, mat2str(fallbackEpochIds));
        fallbackTiming = transformPathEpochs(outputPath, pathName, nRois, ...
            analysisEpoch(pathIdx,:), trialOffsets, trialNumSamples(pathIdx,:), ...
            sampleRateHz, params, fallbackEpochIds);
        timing.fallback_read_s = timing.fallback_read_s + fallbackTiming.read_s;
        timing.derived_compute_s = timing.derived_compute_s + fallbackTiming.compute_s;
        timing.derived_write_s = timing.derived_write_s + fallbackTiming.write_s;
    end

    timing.total_s = toc(pathTimer);
    summary.timing.path(pathIdx) = timing;
    summary.path(pathIdx).timing = timing;

end

summary.timing.total_s = toc(runTimer);

if totalVoltageRoisFound == 0
    % Do not leave behind a superficially valid but scientifically empty output.
    if exist(outputPath,'file') == 2
        delete(outputPath);
    end
    error('Voltage:NoVoltageROIs', ...
        ['No Voltage ROIs were found on any imaging path. Acquisition ROI masks ' ...
         'were tested against integration-mode membership in each SLAP2 parse plan, ' ...
         'and none mapped to integration samples. No fluorescence data were extracted.']);
end

fprintf('\nVoltage extraction complete in %.1f s:\n  %s\n', summary.timing.total_s, outputPath);
catch ME
    cleanupPartialOutput(outputPath,ME);
    rethrow(ME);
end
end

function cleanupPartialOutput(outputPath,originalError)
%CLEANUPPARTIALOUTPUT Remove an incomplete HDF5 product after any failed run.
if exist(outputPath,'file') ~= 2
    return
end
try
    delete(outputPath);
    fprintf(2,'Removed incomplete Voltage output after failure: %s\n',outputPath);
catch cleanupError
    warning('Voltage:PartialOutputCleanupFailed', ...
        ['Voltage failed with %s, and the incomplete output could not be removed: %s. ' ...
         'Delete it manually before rerunning.'], ...
        originalError.identifier, cleanupError.message);
end
end

function path = resolveTrialTablePath(inputPath)
inputPath = char(string(inputPath));
if exist(inputPath,'dir')
    path = fullfile(inputPath,'trial_table.h5');
else
    path = inputPath;
end
if exist(path,'file') ~= 2
    error('Voltage:TrialTableNotFound','Could not find trial table: %s',path);
end
end


function validateTrialTable(t)
required = {'filename','slap2_info'};
for k = 1:numel(required)
    if ~isfield(t,required{k})
        error('Voltage:InvalidTrialTable','trial_table.h5 is missing /%s.',required{k});
    end
end
if ~isfield(t.slap2_info,'first_line') || ~isfield(t.slap2_info,'last_line')
    error('Voltage:InvalidTrialTable','trial_table.h5 must contain slap2_info/first_line and last_line.');
end
end


function [firstLine,lastLine] = normalizeLineRanges(trialTable,filename,firstLineRaw,lastLineRaw)
% New trial tables explicitly store integer inclusive bounds. Legacy GIAnT
% CYCLE tables used the next trial edge as last_line, i.e. a half-open bound.
% Convert both forms to one inclusive integer convention internally.
firstLine = round(firstLineRaw);
lastLine = round(lastLineRaw);
convention = '';
if isfield(trialTable,'slap2_info') && isfield(trialTable.slap2_info,'line_range_convention')
    convention = lower(strtrim(char(string(trialTable.slap2_info.line_range_convention))));
end
if strcmp(convention,'inclusive')
    return
end
for p = 1:size(filename,1)
    for t = 1:size(filename,2)
        if ~isempty(filename{p,t}) && contains(filename{p,t},'-CYCLE-','IgnoreCase',true)
            lastLine(p,t) = lastLine(p,t)-1;
        end
    end
end
end


function filename = normalizeFilenameGrid(value)
if isstring(value)
    filename = cellstr(value);
elseif iscell(value)
    filename = value;
elseif ischar(value)
    filename = {value};
else
    error('Voltage:InvalidFilenameGrid','trialTable.filename must be a cell/string grid.');
end
for k = 1:numel(filename)
    if isempty(filename{k})
        filename{k} = '';
    else
        filename{k} = char(string(filename{k}));
    end
end
end


function epoch = inferAnalysisEpochs(trialTable, filename)
[nPaths,nTrials] = size(filename);
epoch = ones(nPaths,nTrials);
explicit = [];
if isfield(trialTable,'epoch')
    explicit = double(trialTable.epoch);
end
for p = 1:nPaths
    useExplicit = ~isempty(explicit) && isequal(size(explicit),size(filename));
    if useExplicit
        vals = explicit(p,:);
        validVals = vals(isfinite(vals));
        useExplicit = numel(unique(validVals)) > 1;
    end
    if useExplicit
        epoch(p,:) = relabelStable(vals);
        continue
    end

    current = 1;
    previousPrefix = '';
    for t = 1:nTrials
        if isempty(filename{p,t})
            epoch(p,t) = current;
            continue
        end
        prefix = acquisitionPrefix(filename{p,t});
        if isempty(previousPrefix)
            previousPrefix = prefix;
        elseif ~strcmp(prefix,previousPrefix)
            current = current + 1;
            previousPrefix = prefix;
        end
        epoch(p,t) = current;
    end
end
end


function out = relabelStable(vals)
out = ones(size(vals));
seen = [];
next = 0;
for k = 1:numel(vals)
    v = vals(k);
    if ~isfinite(v)
        out(k) = max(1,next);
        continue
    end
    idx = find(seen==v,1,'first');
    if isempty(idx)
        next = next + 1;
        seen(next) = v; %#ok<AGROW>
        idx = next;
    end
    out(k) = idx;
end
end


function prefix = acquisitionPrefix(fn)
[~,name,~] = fileparts(char(fn));
prefix = regexprep(name,'_DMD\d+.*$','');
prefix = regexprep(prefix,'-DMD\d+.*$','');
if isempty(prefix), prefix = name; end
end


function dataDir = resolveDataDir(trialTable, trialTableDir)
dataDir = '';
if isfield(trialTable,'datadr') && ~isempty(trialTable.datadr)
    dataDir = char(string(trialTable.datadr));
end
if isempty(dataDir)
    candidate = fullfile(trialTableDir,'dynamic_data');
    if isfolder(candidate)
        dataDir = candidate;
    else
        dataDir = trialTableDir;
    end
end
end


function path = resolveDataFilePath(dataDir, trialTableDir, filename)
filename = char(filename);
candidates = {filename, fullfile(dataDir,filename), fullfile(trialTableDir,filename), ...
    fullfile(trialTableDir,'dynamic_data',filename)};
for k = 1:numel(candidates)
    if exist(candidates{k},'file') == 2
        path = candidates{k};
        return
    end
end
error('Voltage:MissingDataFile','Could not find raw SLAP2 file: %s',filename);
end


function [masks, sourceRoiIdx, discovery] = discoverVoltageROIs(hMDF,zIdx,chIdx)
%DISCOVERVOLTAGEROIS Find acquisition ROIs that map to integration samples.
%
% Do not trust the optional ROI.imagingMode label as the scientific selector.
% Legacy voltage recordings can contain valid integration ROIs whose metadata
% label is absent or uses a different spelling/value. Instead, reconstruct each
% acquisition ROI mask and ask the same SLAP2 Trace/parse-plan machinery used by
% extraction whether that mask has integration-pixel mappings.
%
% Classification intentionally uses integrationPixels ONLY. The later raw-F
% extraction still calls Trace.setPixelIdxs(mask,mask), preserving the optimized
% legacy extraction calculation exactly.
meta = hMDF.metaData;
if ~isfield(meta,'AcquisitionContainer') || ...
        ~isfield(meta.AcquisitionContainer,'ROIs') || ...
        ~isfield(meta.AcquisitionContainer.ROIs,'rois')
    error('Voltage:MissingAcquisitionROIs', ...
        'SLAP2 metadata are missing AcquisitionContainer.ROIs.rois.');
end

rois = meta.AcquisitionContainer.ROIs.rois;
if ~iscell(rois), rois = num2cell(rois); end
nAcquisitionRois = numel(rois);
nRows = double(meta.dmdPixelsPerColumn);
nCols = double(meta.dmdPixelsPerRow);

candidateMasks = false(nRows,nCols,nAcquisitionRois);
isVoltage = false(1,nAcquisitionRois);
integrationSuperPixelCounts = zeros(1,nAcquisitionRois);
imagingMode = cell(1,nAcquisitionRois);

for i = 1:nAcquisitionRois
    roi = rois{i};
    candidateMasks(:,:,i) = buildAcquisitionRoiMask(roi,nRows,nCols,i);
    imagingMode{i} = safeRoiModeString(getRoiField(roi,'imagingMode',''));

    % This performs parse-plan mapping only; TracePixel data are not loaded until
    % Trace.process/processAsync. Therefore ROI discovery does not read the full
    % fluorescence trace from disk.
    hTrace = slap2.util.datafile.trace.Trace(hMDF,zIdx,chIdx);
    hTrace.setPixelIdxs([],candidateMasks(:,:,i));
    integrationSuperPixelCounts(i) = numel(hTrace.TracePixels);
    isVoltage(i) = integrationSuperPixelCounts(i) > 0;
    clear hTrace
end

sourceRoiIdx = find(isVoltage);
masks = candidateMasks(:,:,isVoltage);

discovery = struct();
discovery.method = 'parse_plan_integration_membership';
discovery.nAcquisitionROIs = nAcquisitionRois;
discovery.nVoltageROIs = numel(sourceRoiIdx);
discovery.sourceRoiIdx = sourceRoiIdx;
discovery.integrationSuperPixelCounts = integrationSuperPixelCounts;
discovery.imagingMode = imagingMode;
end


function mask = buildAcquisitionRoiMask(roi,nRows,nCols,sourceRoiIdx)
stored = getRoiField(roi,'mask',[]);
if ~isempty(stored)
    mask = logical(stored);
    if ndims(mask)>2 && size(mask,3)==1, mask = mask(:,:,1); end
    if isequal(size(mask),[nCols,nRows]), mask = mask.'; end
    if ~isequal(size(mask),[nRows,nCols])
        error('Voltage:UnexpectedMaskSize', ...
            'Acquisition ROI %d mask size is %s; expected [%d %d].', ...
            sourceRoiIdx,mat2str(size(mask)),nRows,nCols);
    end
else
    shape = double(getRoiField(roi,'shapeData',[]));
    if isempty(shape) || size(shape,2)<2
        error('Voltage:MissingRoiMask', ...
            'Acquisition ROI %d has no usable mask/shapeData.',sourceRoiIdx);
    end
    shape = round(shape(:,1:2));
    valid = shape(:,1)>=1 & shape(:,1)<=nRows & shape(:,2)>=1 & shape(:,2)<=nCols;
    if ~all(valid)
        warning('Voltage:RoiShapeOutOfBounds', ...
            'Acquisition ROI %d has %d out-of-bounds shapeData pixels; ignoring them.', ...
            sourceRoiIdx,nnz(~valid));
    end
    shape = shape(valid,:);
    mask = false(nRows,nCols);
    if ~isempty(shape)
        mask(sub2ind(size(mask),shape(:,1),shape(:,2))) = true;
    end
end

if ~any(mask(:))
    warning('Voltage:EmptyAcquisitionROI', ...
        'Acquisition ROI %d produced an empty image-space mask.',sourceRoiIdx);
end
end


function value = safeRoiModeString(value)
try
    if isempty(value)
        value = '';
    elseif ischar(value)
        % preserve
    elseif isstring(value) && isscalar(value)
        value = char(value);
    elseif isnumeric(value) || islogical(value)
        value = mat2str(value);
    else
        value = char(string(value));
    end
catch
    value = sprintf('<%s>',class(value));
end
end

function value = getRoiField(roi,name,defaultValue)
value = defaultValue;
if isstruct(roi) && isfield(roi,name)
    value = roi.(name);
elseif isobject(roi) && isprop(roi,name)
    value = roi.(name);
end
end


function rate = resolveSampleRateHz(hMDF)
if isfield(hMDF.metaData,'linePeriod_s') && ~isempty(hMDF.metaData.linePeriod_s)
    rate = 1/double(hMDF.metaData.linePeriod_s);
elseif isfield(hMDF.metaData,'AcquisitionContainer') && ...
        isfield(hMDF.metaData.AcquisitionContainer,'ParsePlan') && ...
        isfield(hMDF.metaData.AcquisitionContainer.ParsePlan,'lineRateHz')
    rate = double(hMDF.metaData.AcquisitionContainer.ParsePlan.lineRateHz);
else
    error('Voltage:MissingSampleRate','Could not resolve SLAP2 line/sample rate.');
end
validateattributes(rate,{'numeric'},{'scalar','real','finite','positive'});
end


function z = resolveZDepth(hMDF)
z = NaN;
if isprop(hMDF,'fastZs') && ~isempty(hMDF.fastZs)
    z = double(hMDF.fastZs(1));
elseif isfield(hMDF.metaData,'AcquisitionContainer') && ...
        isfield(hMDF.metaData.AcquisitionContainer,'ParsePlan') && ...
        isfield(hMDF.metaData.AcquisitionContainer.ParsePlan,'zs')
    vals = double(hMDF.metaData.AcquisitionContainer.ParsePlan.zs);
    if ~isempty(vals), z = vals(1); end
end
end


function meta = getGeometryMeta(hMDF)
meta = struct();
fields = {'dmdPixelsPerRow','dmdPixelsPerColumn','samplesPerLine','channelsSave'};
for k = 1:numel(fields)
    name = fields{k};
    if isfield(hMDF.metaData,name), meta.(name) = hMDF.metaData.(name); else, meta.(name) = []; end
end
meta.linesPerCycle = hMDF.header.linesPerCycle;
end


function validateSourceCompatibility(pathIdx, sourceName, canonicalMeta, sourceMeta, ...
    canonicalMasks, sourceMasks, canonicalSourceRoiIdx, sourceRoiIdx, canonicalRate, sourceRate)
fields = fieldnames(canonicalMeta);
for k = 1:numel(fields)
    name = fields{k};
    if ~isequal(canonicalMeta.(name),sourceMeta.(name))
        error('Voltage:IncompatibleSource','Path%d source %s changed %s.',pathIdx,sourceName,name);
    end
end
if ~isequal(size(canonicalMasks),size(sourceMasks)) || ~isequal(canonicalMasks,sourceMasks)
    error('Voltage:IncompatibleSourceROIs','Path%d source %s has different integration ROI masks.',pathIdx,sourceName);
end
if ~isequal(double(canonicalSourceRoiIdx(:)),double(sourceRoiIdx(:)))
    error('Voltage:IncompatibleSourceROIs','Path%d source %s changed integration ROI order/identity.',pathIdx,sourceName);
end
if abs(double(canonicalRate)-double(sourceRate)) > max(1e-9,1e-9*abs(double(canonicalRate)))
    error('Voltage:IncompatibleSampleRate','Path%d source %s changed sample rate.',pathIdx,sourceName);
end
end


function validateParsePlanCompatibility(hMDF,pathIdx)
required = {'lineSuperPixelIDs','lineFastZIdxs','zPixelReplacementMaps'};
for k = 1:numel(required)
    if ~isprop(hMDF,required{k})
        error('Voltage:ParsePlanMissingField','Path%d MultiDataFiles is missing %s.',pathIdx,required{k});
    end
end
if isempty(hMDF.zPixelReplacementMaps) || isempty(hMDF.lineSuperPixelIDs)
    error('Voltage:EmptyParsePlan','Path%d has an empty SLAP2 parse plan.',pathIdx);
end
end


function [offsets,total] = computeTrialOffsets(lengths)
lengths = double(lengths(:)');
offsets = zeros(size(lengths));
running = 1;
for t = 1:numel(lengths)
    if lengths(t) > 0
        offsets(t) = running;
        running = running + lengths(t);
    end
end
total = running-1;
end


function initializePathOutput(filename,pathName,masks,sourceRoiIdx,sampleRateHz,zDepth, ...
    trialLengths,trialEpoch,firstLine,lastLine,trialOffsets,params)
writeNumericDataset(filename,[pathName '/Z_depths'],double(zDepth(:)),'double');
writeNumericDataset(filename,[pathName '/sample_rate_hz'],double(sampleRateHz),'double');
writeNumericDataset(filename,[pathName '/frame_info/trial_num_frames'],int32(trialLengths(:)),'int32');
writeNumericDataset(filename,[pathName '/frame_info/trial_epoch'],int32(trialEpoch(:)),'int32');

[~,totalSamples] = computeTrialOffsets(trialLengths);
if totalSamples > 0
    h5create(filename,[pathName '/frame_info/frame_line_idxs'],[totalSamples 1],'Datatype','int32', ...
        'ChunkSize',[min(totalSamples,params.h5ChunkSamples) 1]);
    h5create(filename,[pathName '/frame_info/sample_epoch'],[totalSamples 1],'Datatype','int32', ...
        'ChunkSize',[min(totalSamples,params.h5ChunkSamples) 1]);
    for t = 1:numel(trialLengths)
        n = trialLengths(t);
        if n <= 0, continue, end
        a = round(firstLine(t)); b = round(lastLine(t));
        lines = int32((a:b)');
        if numel(lines) ~= n
            error('Voltage:InternalTrialLengthMismatch','Trial %d line vector length mismatch.',t);
        end
        h5write(filename,[pathName '/frame_info/frame_line_idxs'],lines,[trialOffsets(t) 1],[n 1]);
        h5write(filename,[pathName '/frame_info/sample_epoch'],repmat(int32(trialEpoch(t)),n,1), ...
            [trialOffsets(t) 1],[n 1]);
    end
end

nRois = size(masks,3);
if nRois == 0 || totalSamples == 0
    return
end
nRows = size(masks,1); nCols = size(masks,2);
profiles = zeros(nRois,1,nRows,nCols,'single');
coords = zeros(nRois,3);
pixelCount = zeros(nRois,1,'int32');
[rGrid,cGrid] = ndgrid(1:nRows,1:nCols);
for r = 1:nRois
    mask = masks(:,:,r);
    profiles(r,1,:,:) = reshape(single(mask),1,1,nRows,nCols);
    pixelCount(r) = int32(nnz(mask));
    if any(mask(:))
        coords(r,2) = mean(rGrid(mask))-1;
        coords(r,3) = mean(cGrid(mask))-1;
    end
end
writeNumericDataset(filename,[pathName '/sources/spatial/profiles'],profiles,'single');
writeNumericDataset(filename,[pathName '/sources/spatial/coords'],coords,'double');
writeNumericDataset(filename,[pathName '/sources/spatial/source_roi_index'],int32(sourceRoiIdx(:)),'int32');
writeNumericDataset(filename,[pathName '/sources/spatial/roi_pixel_count'],pixelCount,'int32');

createTemporalDataset(filename,[pathName '/sources/temporal/raw_f'],nRois,totalSamples,params);
createTemporalDataset(filename,[pathName '/sources/temporal/f0'],nRois,totalSamples,params);
createTemporalDataset(filename,[pathName '/sources/temporal/dff'],nRois,totalSamples,params);
h5writeatt(filename,[pathName '/sources/temporal/dff'],'sign_convention', ...
    'Positive dff corresponds to positive membrane-voltage deflection.');
h5writeatt(filename,[pathName '/sources/temporal/dff'],'indicator_direction',params.indicatorDirection);
h5writeatt(filename,[pathName '/sources/temporal/dff'],'indicator_name',params.indicatorName);
end


function writeNumericDataset(filename,path,value,datatype)
dims = size(value);
if isscalar(value), dims = [1 1]; end
h5create(filename,path,dims,'Datatype',datatype);
h5write(filename,path,value);
end


function createTemporalDataset(filename,path,nRois,totalSamples,params)
chunk = [1 1 min(totalSamples,params.h5ChunkSamples)];
args = {filename,path,[nRois 1 totalSamples],'Datatype',params.precision, ...
    'ChunkSize',chunk,'FillValue',cast(NaN,params.precision)};
if params.h5Deflate > 0
    args = [args {'Deflate',params.h5Deflate}]; %#ok<AGROW>
end
h5create(args{:});
end


function [traces,errors] = extractRoiBatch(hMDF,masks,batch,params)
traces = cell(1,numel(batch));
errors = cell(1,numel(batch));
if params.useParallel
    futures = cell(1,numel(batch));
    holders = cell(1,numel(batch));
    for j = 1:numel(batch)
        try
            roiIdx = batch(j);
            hTrace = slap2.util.datafile.trace.Trace(hMDF,params.zIdx,params.chIdx);
            mask = masks(:,:,roiIdx);
            hTrace.setPixelIdxs(mask,mask);
            futures{j} = hTrace.processAsync(params.traceWindow_lines,params.traceExpectedWindow_lines);
            holders{j} = hTrace; %#ok<NASGU>
        catch ME
            errors{j} = getReport(ME,'extended','hyperlinks','off');
        end
    end
    for j = 1:numel(batch)
        if ~isempty(errors{j}) || isempty(futures{j}), continue, end
        try
            traces{j} = fetchOutputs(futures{j});
        catch ME
            errors{j} = getReport(ME,'extended','hyperlinks','off');
        end
    end
else
    for j = 1:numel(batch)
        try
            roiIdx = batch(j);
            hTrace = slap2.util.datafile.trace.Trace(hMDF,params.zIdx,params.chIdx);
            mask = masks(:,:,roiIdx);
            hTrace.setPixelIdxs(mask,mask);
            traces{j} = hTrace.process(params.traceWindow_lines,params.traceExpectedWindow_lines);
            clear hTrace
        catch ME
            errors{j} = getReport(ME,'extended','hyperlinks','off');
        end
    end
end
end


function nWrites = writeRawSourceSlices(filename,pathName,trace,roiIdx,trialIndices, ...
    firstLine,lastLine,trialOffsets,trialLengths)
%WRITERAWSOURCESLICES Write one source trace with a contiguous fast path.
dset = [pathName '/sources/temporal/raw_f'];
trials = sort(reshape(trialIndices,1,[]));
trials = trials(trialLengths(trials) > 0);
nWrites = 0;
if isempty(trials), return, end

if trialsAreContiguousInSourceAndOutput(trials,firstLine,lastLine,trialOffsets,trialLengths)
    n = sum(trialLengths(trials));
    a = round(firstLine(trials(1)));
    b = round(lastLine(trials(end)));
    if a < 1 || b > numel(trace) || b < a
        error('Voltage:TraceTooShort', ...
            'ROI%d contiguous source range [%d %d] is outside extracted trace length %d.', ...
            roiIdx,a,b,numel(trace));
    end
    seg = trace(a:b);
    if numel(seg) ~= n
        error('Voltage:TraceLengthMismatch', ...
            'ROI%d contiguous source block expected %d samples but extracted %d.',roiIdx,n,numel(seg));
    end
    h5write(filename,dset,reshape(seg,1,1,n), ...
        [roiIdx 1 trialOffsets(trials(1))],[1 1 n]);
    nWrites = 1;
    return
end

for t = trials
    n = trialLengths(t);
    a = max(1,round(firstLine(t)));
    b = min(numel(trace),round(lastLine(t)));
    if b < a
        error('Voltage:TraceTooShort','ROI%d trial%d range [%d %d] is outside extracted trace length %d.', ...
            roiIdx,t,a,b,numel(trace));
    end
    seg = trace(a:b);
    if numel(seg) ~= n
        error('Voltage:TraceLengthMismatch', ...
            'ROI%d trial%d expected %d samples but extracted %d.',roiIdx,t,n,numel(seg));
    end
    h5write(filename,dset,reshape(seg,1,1,n), ...
        [roiIdx 1 trialOffsets(t)],[1 1 n]);
    nWrites = nWrites + 1;
end
end


function tf = trialsAreContiguousInSourceAndOutput(trials,firstLine,lastLine,trialOffsets,trialLengths)
tf = true;
if numel(trials) <= 1, return, end
for k = 1:(numel(trials)-1)
    t0 = trials(k);
    t1 = trials(k+1);
    sourceContiguous = round(firstLine(t1)) == round(lastLine(t0)) + 1;
    outputContiguous = trialOffsets(t1) == trialOffsets(t0) + trialLengths(t0);
    if ~sourceContiguous || ~outputContiguous
        tf = false;
        return
    end
end
end


function epochIds = completeEpochsForSource(sourceTrials,validTrials,trialEpoch)
%COMPLETEEPOCHSFORSOURCE Return epochs wholly represented by one raw source.
epochIds = [];
if isempty(sourceTrials), return, end
candidates = unique(trialEpoch(sourceTrials),'stable');
for e = reshape(candidates,1,[])
    sourceInEpoch = sort(sourceTrials(trialEpoch(sourceTrials)==e));
    allInEpoch = sort(validTrials(trialEpoch(validTrials)==e));
    if isequal(sourceInEpoch,allInEpoch)
        epochIds(end+1) = e; %#ok<AGROW>
    end
end
end


function out = appendUniqueStable(out,values)
for v = reshape(values,1,[])
    if ~any(out == v)
        out(end+1) = v; %#ok<AGROW>
    end
end
end


function rawEpoch = concatenateTraceTrials(trace,trials,firstLine,lastLine,trialLengths)
%CONCATENATETRACETRIALS Assemble exactly the temporal axis saved for one epoch.
trials = sort(reshape(trials,1,[]));
trials = trials(trialLengths(trials) > 0);
if isempty(trials)
    rawEpoch = zeros(0,1,'like',trace);
    return
end

% Common CYCLE fast path: one contiguous slice from the source trace.
sourceContiguous = true;
for k = 1:(numel(trials)-1)
    if round(firstLine(trials(k+1))) ~= round(lastLine(trials(k))) + 1
        sourceContiguous = false;
        break
    end
end
if sourceContiguous
    a = round(firstLine(trials(1)));
    b = round(lastLine(trials(end)));
    if a < 1 || b > numel(trace) || b < a
        error('Voltage:TraceTooShort', ...
            'Epoch source range [%d %d] is outside extracted trace length %d.',a,b,numel(trace));
    end
    rawEpoch = trace(a:b);
    expected = sum(trialLengths(trials));
    if numel(rawEpoch) ~= expected
        error('Voltage:TraceLengthMismatch', ...
            'Epoch expected %d samples but contiguous source slice contains %d.',expected,numel(rawEpoch));
    end
    rawEpoch = rawEpoch(:);
    return
end

nTotal = sum(trialLengths(trials));
rawEpoch = zeros(nTotal,1,'like',trace);
off = 1;
for t = trials
    n = trialLengths(t);
    a = round(firstLine(t));
    b = round(lastLine(t));
    if a < 1 || b > numel(trace) || b < a
        error('Voltage:TraceTooShort', ...
            'Trial%d source range [%d %d] is outside extracted trace length %d.',t,a,b,numel(trace));
    end
    seg = trace(a:b);
    if numel(seg) ~= n
        error('Voltage:TraceLengthMismatch', ...
            'Trial%d expected %d samples but source slice contains %d.',t,n,numel(seg));
    end
    rawEpoch(off:off+n-1) = seg(:);
    off = off+n;
end
end


function writeDerivedEpoch(filename,pathName,roiIdx,trials,trialOffsets,trialLengths,f0,dff)
trials = sort(reshape(trials,1,[]));
trials = trials(trialLengths(trials) > 0);
if isempty(trials), return, end
nEpoch = sum(trialLengths(trials));
if numel(f0) ~= nEpoch || numel(dff) ~= nEpoch
    error('Voltage:DerivedLengthMismatch', ...
        'Derived epoch length mismatch: expected %d, f0=%d, dff=%d.',nEpoch,numel(f0),numel(dff));
end
firstOffset = trialOffsets(trials(1));
if firstOffset < 1
    error('Voltage:InvalidTrialOffset','Invalid output offset for trial %d.',trials(1));
end
% Complete analysis epochs occupy one contiguous block on the output axis.
for k = 1:(numel(trials)-1)
    t0 = trials(k); t1 = trials(k+1);
    if trialOffsets(t1) ~= trialOffsets(t0) + trialLengths(t0)
        error('Voltage:DisjointEpoch','Epoch trials are not contiguous on the output axis.');
    end
end
h5write(filename,[pathName '/sources/temporal/f0'],reshape(f0,1,1,nEpoch), ...
    [roiIdx 1 firstOffset],[1 1 nEpoch]);
h5write(filename,[pathName '/sources/temporal/dff'],reshape(dff,1,1,nEpoch), ...
    [roiIdx 1 firstOffset],[1 1 nEpoch]);
end


function timing = transformPathEpochs(filename,pathName,nRois,trialEpoch,trialOffsets, ...
    trialLengths,sampleRateHz,params,epochIds)
%TRANSFORMPATHEPOCHS HDF5 fallback for epochs spanning multiple raw files.
timing = struct('read_s',0,'compute_s',0,'write_s',0);
validTrials = find(trialLengths > 0);
if isempty(validTrials) || isempty(epochIds), return, end
rawPath = [pathName '/sources/temporal/raw_f'];
f0Path = [pathName '/sources/temporal/f0'];
dffPath = [pathName '/sources/temporal/dff'];

for roiIdx = 1:nRois
    for e = reshape(epochIds,1,[])
        trials = validTrials(trialEpoch(validTrials)==e);
        if isempty(trials), continue, end
        expected = min(trials):max(trials);
        expected = expected(trialLengths(expected)>0);
        if ~isequal(trials,expected)
            error('Voltage:DisjointEpoch','Path epoch %d occurs in disjoint trial blocks.',e);
        end
        firstOffset = trialOffsets(trials(1));
        nEpoch = sum(trialLengths(trials));

        readTimer = tic;
        raw = h5read(filename,rawPath,[roiIdx 1 firstOffset],[1 1 nEpoch]);
        raw = reshape(raw,[],1);
        timing.read_s = timing.read_s + toc(readTimer);

        computeTimer = tic;
        [f0,~] = computeVoltageF0(raw,sampleRateHz,params);
        [dff,~] = computeVoltageDFF(raw,f0,params.indicatorName,params.indicatorDirection,params.precision);
        timing.compute_s = timing.compute_s + toc(computeTimer);

        writeTimer = tic;
        h5write(filename,f0Path,reshape(f0,1,1,nEpoch),[roiIdx 1 firstOffset],[1 1 nEpoch]);
        h5write(filename,dffPath,reshape(dff,1,1,nEpoch),[roiIdx 1 firstOffset],[1 1 nEpoch]);
        timing.write_s = timing.write_s + toc(writeTimer);
    end
end
end


function bootstrapRepositoryPaths()
%BOOTSTRAPREPOSITORYPATHS Make direct `Voltage` calls self-contained.
% Add only repository-local helper/package roots. The full SLAP2 binary reader
% (MultiDataFiles/Slap2DataFile) remains an external installation.
root = fileparts(mfilename('fullpath'));
paths = { ...
    fullfile(root,'source_extraction'), ...
    fullfile(root,'dependencies','io'), ...
    fullfile(root,'dependencies','gui'), ...
    fullfile(root,'dependencies','slap2_trace'), ...
    fullfile(root,'presets')};
for k = 1:numel(paths)
    if exist(paths{k},'dir') == 7
        addpath(paths{k},'-begin');
    end
end

if isempty(which('slap2.util.MultiDataFiles'))
    error('Voltage:MissingSLAP2Reader', ...
        ['Cannot resolve slap2.util.MultiDataFiles. Install/add the full SLAP2 ' ...
         'binary reader package before running Voltage.']);
end
if isempty(which('slap2.util.datafile.trace.Trace')) || ...
        isempty(which('slap2.util.datafile.trace.TracePixel'))
    error('Voltage:MissingVendoredTraceKernel', ...
        'Repository-local Trace/TracePixel classes did not resolve. Run setup for diagnostics.');
end
end


function timing = emptyTiming()
timing = struct( ...
    'metadata_s',0, ...
    'source_open_s',0, ...
    'output_init_s',0, ...
    'raw_trace_s',0, ...
    'raw_write_s',0, ...
    'raw_h5_writes',0, ...
    'fallback_read_s',0, ...
    'derived_compute_s',0, ...
    'derived_write_s',0, ...
    'total_s',0);
end


function batches = makeBatches(items,batchSize)
if isempty(items), batches = {}; return, end
batchSize = max(1,round(batchSize));
n = ceil(numel(items)/batchSize);
batches = cell(1,n);
for k = 1:n
    a = (k-1)*batchSize+1;
    b = min(numel(items),k*batchSize);
    batches{k} = items(a:b);
end
end


function params = configureParallelPool(params)
if ~params.useParallel, return, end
try
    p = gcp('nocreate');
    if isempty(p)
        parpool('processes',params.nWorkers);
    elseif p.NumWorkers ~= params.nWorkers
        delete(p);
        parpool('processes',params.nWorkers);
    end
catch ME
    warning('Voltage:ParallelPoolFailed','Parallel pool unavailable; using synchronous extraction: %s',ME.message);
    params.useParallel = false;
end
end


function trace = castTrace(trace,precision)
if strcmpi(precision,'double')
    trace = double(trace(:));
else
    trace = single(trace(:));
end
end
