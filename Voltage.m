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
% raw_f is the direct SLAP2 Trace output. F0 and dff are calculated after raw
% extraction, independently within inferred acquisition epochs. No motion
% correction is performed.

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

rootPayload = struct();
rootPayload.format_version = '0.2.0';
rootPayload.params = params;
saveStructToH5(rootPayload, outputPath);

summary = struct();
summary.trialTablePath = trialTablePath;
summary.outputPath = outputPath;
summary.params = params;
summary.nPaths = nPaths;
summary.nTrials = nTrials;
summary.path = repmat(struct(),1,nPaths);

% Configure workers before the extraction pass. HDF5 writes remain serial.
params = configureParallelPool(params);
summary.params = params;

for pathIdx = 1:nPaths
    fprintf('\n=== Voltage Path%d/%d ===\n', pathIdx, nPaths);
    validTrials = find(~cellfun(@isempty, filename(pathIdx,:)) & trialNumSamples(pathIdx,:) > 0);
    if isempty(validTrials)
        warning('Voltage:NoValidTrials', 'Path%d has no valid trials; skipping.', pathIdx);
        continue
    end

    dataDir = resolveDataDir(trialTable, trialTableDir);
    firstSource = resolveDataFilePath(dataDir, trialTableDir, filename{pathIdx,validTrials(1)});
    hMDF = slap2.util.MultiDataFiles(firstSource);
    validateParsePlanCompatibility(hMDF, pathIdx);
    [masks, sourceRoiIdx] = getIntegrationMasks(hMDF);
    if isempty(sourceRoiIdx)
        warning('Voltage:NoIntegrationROIs', 'Path%d has no integration ROIs; skipping source datasets.', pathIdx);
    end
    sampleRateHz = resolveSampleRateHz(hMDF);
    zDepth = resolveZDepth(hMDF);
    canonicalMeta = getGeometryMeta(hMDF);
    delete(hMDF); clear hMDF

    nRois = size(masks,3);
    [trialOffsets, totalSamples] = computeTrialOffsets(trialNumSamples(pathIdx,:));
    pathName = sprintf('/Path%d',pathIdx);
    initializePathOutput(outputPath, pathName, masks, sourceRoiIdx, ...
        sampleRateHz, zDepth, trialNumSamples(pathIdx,:), analysisEpoch(pathIdx,:), ...
        firstLine(pathIdx,:), lastLine(pathIdx,:), trialOffsets, params);

    summary.path(pathIdx).nROIs = nRois;
    summary.path(pathIdx).sampleRateHz = sampleRateHz;
    summary.path(pathIdx).totalSamples = totalSamples;
    summary.path(pathIdx).trialNumSamples = trialNumSamples(pathIdx,:);
    summary.path(pathIdx).trialEpoch = analysisEpoch(pathIdx,:);

    if nRois == 0
        continue
    end

    % Extract each distinct raw source file once. Continuous CYCLE pseudo-trials
    % usually point repeatedly to the same first CYCLE file, so this avoids
    % reprocessing the full acquisition for every pseudo-trial.
    sourceFiles = filename(pathIdx,validTrials);
    [uniqueSources,~,sourceGroup] = unique(sourceFiles,'stable');
    for sourceIdx = 1:numel(uniqueSources)
        sourceName = uniqueSources{sourceIdx};
        sourceTrials = validTrials(sourceGroup == sourceIdx);
        sourcePath = resolveDataFilePath(dataDir, trialTableDir, sourceName);
        fprintf('Path%d source %d/%d: %s\n', pathIdx, sourceIdx, numel(uniqueSources), sourceName);

        hMDF = slap2.util.MultiDataFiles(sourcePath);
        validateParsePlanCompatibility(hMDF, pathIdx);
        [sourceMasks, sourceRoiIdxNow] = getIntegrationMasks(hMDF);
        validateSourceCompatibility(pathIdx, sourceName, canonicalMeta, getGeometryMeta(hMDF), ...
            masks, sourceMasks, sourceRoiIdx, sourceRoiIdxNow, sampleRateHz, resolveSampleRateHz(hMDF));

        batches = makeBatches(1:nRois, params.maxConcurrentROIs);
        for batchIdx = 1:numel(batches)
            batch = batches{batchIdx};
            fprintf('  ROI batch %d/%d: %s\n', batchIdx, numel(batches), mat2str(batch));
            [traces, errors] = extractRoiBatch(hMDF, masks, batch, params);
            for j = 1:numel(batch)
                roiIdx = batch(j);
                if ~isempty(errors{j})
                    error('Voltage:ROIExtractionFailed', ...
                        'Path%d ROI%d failed for %s:\n%s', pathIdx, roiIdx, sourceName, errors{j});
                end
                trace = castTrace(traces{j}, params.precision);
                writeRawTrialSlices(outputPath, pathName, trace, roiIdx, sourceTrials, ...
                    firstLine(pathIdx,:), lastLine(pathIdx,:), trialOffsets, trialNumSamples(pathIdx,:));
            end
        end
        delete(hMDF); clear hMDF
    end

    % Compute F0/dF/F after raw extraction. Reading one ROI/epoch at a time keeps
    % the memory footprint bounded and gives both continuous and trial-file data
    % the same epoch-scoped baseline behavior.
    fprintf('Computing epoch-scoped F0 and dF/F for Path%d...\n', pathIdx);
    transformPath(outputPath, pathName, nRois, analysisEpoch(pathIdx,:), ...
        trialOffsets, trialNumSamples(pathIdx,:), sampleRateHz, params);
end

fprintf('\nVoltage extraction complete:\n  %s\n', outputPath);
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


function [masks, sourceRoiIdx] = getIntegrationMasks(hMDF)
meta = hMDF.metaData;
rois = meta.AcquisitionContainer.ROIs.rois;
if ~iscell(rois), rois = num2cell(rois); end
isIntegration = false(1,numel(rois));
for i = 1:numel(rois)
    mode = getRoiField(rois{i},'imagingMode','');
    isIntegration(i) = strcmpi(char(mode),'Integrate');
end
sourceRoiIdx = find(isIntegration);
selected = rois(isIntegration);
nRows = double(meta.dmdPixelsPerColumn);
nCols = double(meta.dmdPixelsPerRow);
masks = false(nRows,nCols,numel(selected));
for i = 1:numel(selected)
    stored = getRoiField(selected{i},'mask',[]);
    if ~isempty(stored)
        mask = logical(stored);
        if ndims(mask)>2 && size(mask,3)==1, mask = mask(:,:,1); end
        if isequal(size(mask),[nCols,nRows]), mask = mask.'; end
        if ~isequal(size(mask),[nRows,nCols])
            error('Voltage:UnexpectedMaskSize','ROI %d mask size is %s; expected [%d %d].', ...
                sourceRoiIdx(i),mat2str(size(mask)),nRows,nCols);
        end
    else
        shape = double(getRoiField(selected{i},'shapeData',[]));
        if isempty(shape) || size(shape,2)<2
            error('Voltage:MissingRoiMask','Integration ROI %d has no usable mask/shapeData.',sourceRoiIdx(i));
        end
        shape = round(shape(:,1:2));
        valid = shape(:,1)>=1 & shape(:,1)<=nRows & shape(:,2)>=1 & shape(:,2)<=nCols;
        shape = shape(valid,:);
        mask = false(nRows,nCols);
        if ~isempty(shape)
            mask(sub2ind(size(mask),shape(:,1),shape(:,2))) = true;
        end
    end
    masks(:,:,i) = mask;
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


function writeRawTrialSlices(filename,pathName,trace,roiIdx,trialIndices,firstLine,lastLine,trialOffsets,trialLengths)
dset = [pathName '/sources/temporal/raw_f'];
for t = reshape(trialIndices,1,[])
    n = trialLengths(t);
    if n <= 0, continue, end
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
    payload = reshape(seg,1,1,n);
    h5write(filename,dset,payload,[roiIdx 1 trialOffsets(t)],[1 1 n]);
end
end


function transformPath(filename,pathName,nRois,trialEpoch,trialOffsets,trialLengths,sampleRateHz,params)
validTrials = find(trialLengths > 0);
if isempty(validTrials), return, end
epochIds = unique(trialEpoch(validTrials),'stable');
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
        raw = h5read(filename,rawPath,[roiIdx 1 firstOffset],[1 1 nEpoch]);
        raw = reshape(raw,[],1);
        [f0,~] = computeVoltageF0(raw,sampleRateHz,params);
        [dff,~] = computeVoltageDFF(raw,f0,params.indicatorName,params.indicatorDirection,params.precision);
        h5write(filename,f0Path,reshape(f0,1,1,nEpoch),[roiIdx 1 firstOffset],[1 1 nEpoch]);
        h5write(filename,dffPath,reshape(dff,1,1,nEpoch),[roiIdx 1 firstOffset],[1 1 nEpoch]);
    end
end
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
