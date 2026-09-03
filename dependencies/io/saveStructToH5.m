function saveStructToH5(s, filename)
%SAVESTRUCTTOH5 Write a (possibly nested) scalar struct to an HDF5 file.
%   SAVESTRUCTTOH5(s, filename) recursively maps MATLAB struct fields onto
%   the HDF5 hierarchy:
%     - Scalar struct fields become HDF5 groups.
%     - Cell arrays of char/string become variable-length string datasets.
%     - char and string scalars/arrays become string datasets.
%     - Numeric and logical arrays become numeric datasets (logicals as int8).
%     - Empty fields are skipped.
%
%   The destination file is overwritten if it already exists; HDF5 datasets
%   cannot be redefined in place so a fresh file is required.
%
%   Dataset sizes match MATLAB size(val). The file includes /row_major
%   (uint8): 0 = column-major (MATLAB layout). See README.md
%   "Reading H5 outside MATLAB".
%
%   HDF5 robustness: dataset creation and immediate reopening can be briefly
%   inconsistent on SMB/network-backed paths. Every create/write operation is
%   therefore verified and retried. This preserves the file schema while
%   avoiding transient "dataset does not exist" failures after H5CREATE.

if nargin < 2 || isempty(filename)
    error('saveStructToH5:MissingFilename', 'A destination filename must be provided.');
end
if ~isstruct(s) || ~isscalar(s)
    error('saveStructToH5:UnsupportedInput', 'Input must be a scalar struct.');
end

if exist(filename, 'file')
    delete(filename);
end

writeGroup(filename, '', s);
createAndWriteDatasetRobust(filename, '/row_major', [1 1], 'uint8', uint8(0));
end


function writeGroup(filename, basePath, s)
%WRITEGROUP Recursively write each field of struct s under basePath.
if ~isstruct(s) || ~isscalar(s)
    error('saveStructToH5:UnsupportedStruct', ...
        'Only scalar structs are supported (at %s).', emptyPathDisplay(basePath));
end

fields = fieldnames(s);
for ix = 1:numel(fields)
    fname = fields{ix};
    path = [basePath '/' fname];
    writeValue(filename, path, s.(fname));
end
end


function writeValue(filename, path, val)
%WRITEVALUE Write a single value to the HDF5 path based on its MATLAB type.
if isstruct(val)
    if ~isscalar(val)
        error('saveStructToH5:NonScalarStruct', ...
            'Non-scalar structs are not supported (at %s).', path);
    end
    writeGroup(filename, path, val);
    return;
end

if iscell(val)
    if isempty(val)
        return;
    end
    isTextCell = all(cellfun(@(x) ischar(x) || isstring(x) || isempty(x), val(:)));
    if ~isTextCell
        error('saveStructToH5:UnsupportedCell', ...
            'Only cell arrays of char/string are supported (at %s).', path);
    end
    sval = strings(size(val));
    for k = 1:numel(val)
        if isempty(val{k})
            sval(k) = "";
        else
            sval(k) = string(val{k});
        end
    end
    createAndWriteDatasetRobust(filename, path, size(sval), 'string', sval);
    return;
end

if ischar(val)
    createAndWriteDatasetRobust(filename, path, [1 1], 'string', string(val));
    return;
end

if isstring(val)
    sz = size(val);
    if isscalar(val)
        sz = [1 1];
    end
    createAndWriteDatasetRobust(filename, path, sz, 'string', val);
    return;
end

if islogical(val)
    if isempty(val)
        return;
    end
    val = int8(val);
    createAndWriteDatasetRobust(filename, path, size(val), 'int8', val);
    return;
end

if isnumeric(val)
    if isempty(val)
        return;
    end
    val = gather(val);          % collect gpuArray / codistributed
    dtype = class(val);
    % Round-trip through cast to materialize a plain array of the declared
    % class without applying per-element arithmetic.
    plainVal = cast(val, dtype);
    createAndWriteDatasetRobust(filename, path, size(plainVal), dtype, plainVal);
    return;
end

error('saveStructToH5:UnsupportedType', ...
    'Unsupported value type ''%s'' at %s.', class(val), path);
end


function createAndWriteDatasetRobust(filename, path, sz, dtype, val)
%CREATEANDWRITEDATASETROBUST Create, verify, then write one HDF5 dataset.
% The high-level MATLAB HDF5 functions reopen the file between H5CREATE and
% H5WRITE. On SMB storage the new dataset can occasionally be temporarily
% invisible to that reopen. Wait for visibility and retry writes rather than
% recreating the entire file or failing a long processing job.

maxCreateAttempts = 4;
maxVisibilityChecks = 10;
maxWriteAttempts = 8;
lastError = [];

% Creation. A failed create may still have committed metadata, so visibility
% is checked independently before another create attempt is made.
for createAttempt = 1:maxCreateAttempts
    if datasetVisible(filename, path)
        break
    end
    try
        h5create(filename, path, sz, 'Datatype', dtype);
    catch ME
        lastError = ME;
    end
    if waitForDataset(filename, path, sz, maxVisibilityChecks)
        break
    end
    if createAttempt < maxCreateAttempts
        pause(backoffSeconds(createAttempt));
    end
end

if ~waitForDataset(filename, path, sz, maxVisibilityChecks)
    if isempty(lastError)
        detail = 'dataset never became visible after creation';
    else
        detail = lastError.message;
    end
    error('saveStructToH5:H5CreateFailed', ...
        'Failed to create/verify HDF5 dataset %s: %s', path, detail);
end

% Writing. Do not recreate a dataset after writing has begun; simply retry
% reopening/writing it if network metadata visibility is transient.
lastError = [];
for writeAttempt = 1:maxWriteAttempts
    try
        h5write(filename, path, val);
        return
    catch ME
        lastError = ME;
        if writeAttempt < maxWriteAttempts
            waitForDataset(filename, path, sz, 2);
            pause(backoffSeconds(writeAttempt));
        end
    end
end
error('saveStructToH5:H5WriteFailed', ...
    'Failed to write HDF5 dataset %s after %d attempts: %s', ...
    path, maxWriteAttempts, lastError.message);
end


function tf = waitForDataset(filename, path, expectedSize, maxChecks)
%WAITFORDATASET Wait for a newly-created dataset to become visible/reopenable.
tf = false;
for checkIx = 1:maxChecks
    try
        info = h5info(filename, path);
        actualSize = double(info.Dataspace.Size);
        if ~isequal(actualSize(:)', double(expectedSize(:)'))
            error('saveStructToH5:H5DatasetSizeMismatch', ...
                'Dataset %s has size [%s], expected [%s].', path, ...
                num2str(actualSize), num2str(expectedSize));
        end
        tf = true;
        return
    catch ME
        % A genuine size mismatch must not be hidden as a transient SMB delay.
        if strcmp(ME.identifier,'saveStructToH5:H5DatasetSizeMismatch')
            rethrow(ME);
        end
        if checkIx < maxChecks
            pause(backoffSeconds(checkIx));
        end
    end
end
end


function tf = datasetVisible(filename, path)
tf = false;
try
    h5info(filename, path);
    tf = true;
catch
end
end


function s = backoffSeconds(attempt)
% Small bounded exponential backoff: 0.05, 0.10, 0.20 ... <= 0.8 s.
s = min(0.8, 0.05 * 2^(max(0,attempt-1)));
end


function s = emptyPathDisplay(basePath)
if isempty(basePath)
    s = '/';
else
    s = basePath;
end
end
