function [xOffset_pix,yOffset_pix,zOffset_um] = getOnlineMotion(hDataFile,lineIds)
%GETONLINEMOTION Read microscope online-motion offsets for global line IDs.
%
% Uses the fastest getLineHeader API supported by the installed SLAP2
% reader, discovered once per reader class and cached across pseudo-trials:
%   1) fully vectorized residual-line + cycle vectors;
%   2) vectorized residual lines grouped by scalar cycle;
%   3) legacy scalar line-header reads.
%
% Output orientation remains nLines x 1 for backward compatibility.

linesPerCycle = numel(hDataFile.lineHeaderIdxs);
numCycles = hDataFile.numCycles;
totalNumLines = linesPerCycle * numCycles;

if nargin<2 || isempty(lineIds)
    lineIds = 1:linesPerCycle:totalNumLines;
end

lineIds = double(lineIds(:));
if any(~isfinite(lineIds)) || any(lineIds ~= round(lineIds)) || ...
        any(lineIds < 1) || any(lineIds > totalNumLines)
    error('getOnlineMotion:InvalidLineIds', ...
        'lineIds must be finite integer indices in [1, %d].',totalNumLines);
end

cycleIdxs = ceil(lineIds/linesPerCycle);
resIdxs = lineIds - (cycleIdxs-1)*linesPerCycle;
nLines = numel(lineIds);

persistent headerModeByClass
if isempty(headerModeByClass)
    headerModeByClass = containers.Map('KeyType','char','ValueType','char');
end
readerClass = class(hDataFile);

% Reuse the capability discovered on an earlier pseudo-trial. If a cached
% fast mode unexpectedly fails, discard it and re-probe safely below.
if isKey(headerModeByClass,readerClass)
    cachedMode = headerModeByClass(readerClass);
    switch cachedMode
        case 'vector'
            [xOffset_pix,yOffset_pix,zOffset_um,ok] = ...
                tryBatchLineHeaders(hDataFile,resIdxs,cycleIdxs,nLines);
            if ok
                return
            end
        case 'cycle-grouped'
            [xOffset_pix,yOffset_pix,zOffset_um,ok] = ...
                tryCycleGroupedLineHeaders(hDataFile,resIdxs,cycleIdxs,nLines);
            if ok
                return
            end
        case 'scalar'
            [xOffset_pix,yOffset_pix,zOffset_um] = ...
                readScalarLineHeaders(hDataFile,resIdxs,cycleIdxs,nLines);
            return
    end
    remove(headerModeByClass,readerClass);
end

% Probe the reader API once. Some Slap2DataReader revisions support multiple
% line headers in one call; others only support vectors within one cycle.
[xOffset_pix,yOffset_pix,zOffset_um,ok] = ...
    tryBatchLineHeaders(hDataFile,resIdxs,cycleIdxs,nLines);
if ok
    headerModeByClass(readerClass) = 'vector';
    return
end

[xOffset_pix,yOffset_pix,zOffset_um,ok] = ...
    tryCycleGroupedLineHeaders(hDataFile,resIdxs,cycleIdxs,nLines);
if ok
    headerModeByClass(readerClass) = 'cycle-grouped';
    return
end

headerModeByClass(readerClass) = 'scalar';
[xOffset_pix,yOffset_pix,zOffset_um] = ...
    readScalarLineHeaders(hDataFile,resIdxs,cycleIdxs,nLines);
end


function [x,y,z] = readScalarLineHeaders(hDataFile,resIdxs,cycleIdxs,nLines)
x = nan(nLines,1);
y = nan(nLines,1);
z = nan(nLines,1);
for idx = 1:nLines
    lineHeader = hDataFile.getLineHeader(resIdxs(idx),cycleIdxs(idx));
    x(idx) = lineHeader.xOffset_pix;
    y(idx) = lineHeader.yOffset_pix;
    z(idx) = lineHeader.zOffset_um;
end
end


function [x,y,z,ok] = tryBatchLineHeaders(hDataFile,resIdxs,cycleIdxs,nLines)
x = [];
y = [];
z = [];
ok = false;

try
    headers = hDataFile.getLineHeader(resIdxs,cycleIdxs);
    [x,y,z,ok] = unpackHeaders(headers,nLines);
catch
    ok = false;
end

% A few APIs distinguish row from column vector inputs. Try the alternate
% orientation once before falling back to cycle-grouped/scalar calls.
if ~ok && nLines>1
    try
        headers = hDataFile.getLineHeader(resIdxs',cycleIdxs');
        [x,y,z,ok] = unpackHeaders(headers,nLines);
    catch
        ok = false;
    end
end
end


function [x,y,z,ok] = tryCycleGroupedLineHeaders(hDataFile,resIdxs,cycleIdxs,nLines)
x = nan(nLines,1);
y = nan(nLines,1);
z = nan(nLines,1);
ok = false;

uniqueCycles = unique(cycleIdxs,'stable');
try
    for cycleIx = 1:numel(uniqueCycles)
        thisCycle = uniqueCycles(cycleIx);
        sel = find(cycleIdxs==thisCycle);
        if numel(sel)==1
            header = hDataFile.getLineHeader(resIdxs(sel),thisCycle);
            [xx,yy,zz,headerOK] = unpackHeaders(header,1);
        else
            headers = hDataFile.getLineHeader(resIdxs(sel),thisCycle);
            [xx,yy,zz,headerOK] = unpackHeaders(headers,numel(sel));
            if ~headerOK
                headers = hDataFile.getLineHeader(resIdxs(sel)',thisCycle);
                [xx,yy,zz,headerOK] = unpackHeaders(headers,numel(sel));
            end
        end
        if ~headerOK
            x = []; y = []; z = [];
            return
        end
        x(sel) = xx;
        y(sel) = yy;
        z(sel) = zz;
    end
    ok = true;
catch
    x = [];
    y = [];
    z = [];
    ok = false;
end
end


function [x,y,z,ok] = unpackHeaders(headers,nLines)
x = [];
y = [];
z = [];
ok = false;

if isstruct(headers)
    if numel(headers)==nLines
        try
            x = reshape([headers.xOffset_pix],[],1);
            y = reshape([headers.yOffset_pix],[],1);
            z = reshape([headers.zOffset_um],[],1);
            ok = numel(x)==nLines && numel(y)==nLines && numel(z)==nLines;
        catch
            ok = false;
        end
    elseif isscalar(headers)
        try
            x = reshape(headers.xOffset_pix,[],1);
            y = reshape(headers.yOffset_pix,[],1);
            z = reshape(headers.zOffset_um,[],1);
            ok = numel(x)==nLines && numel(y)==nLines && numel(z)==nLines;
        catch
            ok = false;
        end
    end
elseif iscell(headers) && numel(headers)==nLines
    try
        x = cellfun(@(h) h.xOffset_pix,headers(:));
        y = cellfun(@(h) h.yOffset_pix,headers(:));
        z = cellfun(@(h) h.zOffset_um,headers(:));
        ok = true;
    catch
        ok = false;
    end
elseif isobject(headers) && numel(headers)==nLines
    try
        x = arrayfun(@(h) h.xOffset_pix,headers(:));
        y = arrayfun(@(h) h.yOffset_pix,headers(:));
        z = arrayfun(@(h) h.zOffset_um,headers(:));
        x = x(:); y = y(:); z = z(:);
        ok = true;
    catch
        ok = false;
    end
end

if ~ok
    x = [];
    y = [];
    z = [];
end
end
