classdef Trace < handle
    properties (SetAccess = private)
        hMultiDataFiles slap2.util.MultiDataFiles;
        zIdx  (1,1) {mustBePositive,mustBeInteger} = 1;
        chIdx (1,1) {mustBePositive,mustBeInteger} = 1;
        TracePixels (:,1) slap2.util.datafile.trace.TracePixel;
        pixelIdxs = [];
    end
    
    properties (Dependent)
        superPixelIds;
    end
    
    methods
        function obj = Trace(hMultiDataFiles,zIdx,chIdx)
            arguments
                hMultiDataFiles (1,1) slap2.util.MultiDataFiles;
                zIdx  (1,1) {mustBePositive,mustBeInteger} = 1;
                chIdx (1,1) {mustBePositive,mustBeInteger} = 1;
            end

            obj.hMultiDataFiles = hMultiDataFiles;
            obj.zIdx = zIdx;
            obj.chIdx = chIdx;
        end
    end

    methods
        function setPixelIdxs(obj,rasterPixels,integrationPixels)
            arguments
                obj
                rasterPixels      = []; % can be a logical map of pixel flags OR a list of indices.
                integrationPixels = []; % can be a logical map of pixel flags OR a list of indices.
            end

            if islogical(rasterPixels) && ~isempty(rasterPixels)
                rasterPixels = checkMapDims(rasterPixels);
                rasterPixels = find(rasterPixels);
            end

            if islogical(integrationPixels) && ~isempty(integrationPixels)
                integrationPixels = checkMapDims(integrationPixels);
                integrationPixels = find(integrationPixels) + numel(integrationPixels);
            end

            validateattributes(rasterPixels, {'numeric'}, {'integer'} ...
                , 'datafile.trace.Trace.setPixelIdxs', 'rasterPixels');
            validateattributes(integrationPixels, {'numeric'}, {'integer'} ...
                , 'datafile.trace.Trace.setPixelIdxs', 'integrationPixels');

            pixelIdxs_ = uint32([rasterPixels(:);integrationPixels(:)]);

            obj.TracePixels = obj.getTracePixels(pixelIdxs_);
            obj.pixelIdxs = pixelIdxs_;

            %%% Nested function
            function map = checkMapDims(map)
                dmdPixelsPerRow = obj.hMultiDataFiles.header.dmdPixelsPerRow;
                dmdPixelsPerColumn = obj.hMultiDataFiles.header.dmdPixelsPerColumn;

                if dmdPixelsPerColumn ~= dmdPixelsPerRow
                    if isequal(size(map),[dmdPixelsPerColumn,dmdPixelsPerRow])
                        map = map';
                    end
                end

                assert(isequal(size(map),[dmdPixelsPerRow,dmdPixelsPerColumn]) ...
                    , 'Incorrect map size. Map needs to be size [%d,%d]' ...
                    , dmdPixelsPerRow, dmdPixelsPerColumn);
            end
        end

        function loadData(obj)
            % probably unneeded. Trace Pixels load on process.
            obj.TracePixels = obj.TracePixels.load();
        end

        function [trace, weight] = process(obj,windowWidth_lines,expectedWindowWidth_lines)
            [obj.TracePixels,trace, weight] = obj.TracePixels.process(windowWidth_lines,expectedWindowWidth_lines);
        end

        function hFuture = processAsync(obj,windowWidth_lines,expectedWindowWidth_lines)
            % windowWidth_lines = 10;
            % expectedWindowWidth_lines = 100;
            hFuture_ = obj.TracePixels.processAsync(windowWidth_lines,expectedWindowWidth_lines);
            hFuture = hFuture_.afterAll(@finalize,2,'PassFuture',true);

            function [trace, weight] = finalize(hFuture)
                [obj.TracePixels,trace, weight] = hFuture.fetchOutputs();
            end
        end
    end

    methods
        function val = get.superPixelIds(obj)
            val = [obj.TracePixels.superPixelId];
        end
    end

    methods (Hidden)
        function TracePixels = getTracePixels(obj,pixelIdxs)
            pixelIDs = unique(pixelIdxs(:)) - 1;
            dmdNumPix = obj.hMultiDataFiles.header.dmdPixelsPerRow*obj.hMultiDataFiles.header.dmdPixelsPerColumn;

            pixelReplacementMap = obj.hMultiDataFiles.zPixelReplacementMaps{obj.zIdx};
            intMask = pixelReplacementMap(:,2) >= dmdNumPix;
            pixelReplacementMap(intMask,1) = pixelReplacementMap(intMask,1) + dmdNumPix;

            [~,sortIdxs] = sort(pixelReplacementMap(:,1));
            pixelReplacementMap = pixelReplacementMap(sortIdxs,:);
            idxs = ismembc2(pixelIDs,pixelReplacementMap(:,1));
            validMask = idxs > 0;
            %validPixelIds = obj.pixelIds(validMask);
            %invalidPixelIds = obj.pixelIds(~validMask);

            idxs = idxs(validMask);
            validSuperPixelIDs = pixelReplacementMap(idxs,2);
            [validCounts,validSuperPixelIDs] = groupcounts(validSuperPixelIDs);

            existingSuperPixelIDs = [obj.TracePixels.superPixelId];
            [~,ia,ib] = intersect(validSuperPixelIDs,existingSuperPixelIDs);
            
            validSuperPixelIDs(ia) = [];
            validCounts(ia) = [];

            ExistingTracePixels = obj.TracePixels(ib);

            NewTracePixel = slap2.util.datafile.trace.TracePixel();
            NewTracePixel.fileNames = {obj.hMultiDataFiles.hDataFiles.filename};
            NewTracePixel.bytesPerCycle = obj.hMultiDataFiles.header.bytesPerCycle; 
            NewTracePixel.firstCycleOffsetBytes = obj.hMultiDataFiles.header.firstCycleOffsetBytes;
            NewTracePixel.linesPerCycle = obj.hMultiDataFiles.header.linesPerCycle;

            NewTracePixels = repmat(NewTracePixel,numel(validSuperPixelIDs),1);

            [superPixelNumPixels,superPixelNumPixelsIDs] = groupcounts(pixelReplacementMap(:,2));
            [~,ia] = intersect(superPixelNumPixelsIDs,validSuperPixelIDs);
            superPixelNumPixels = superPixelNumPixels(ia);

            for idx = 1:numel(NewTracePixels)
                NewTracePixels(idx).superPixelId = validSuperPixelIDs(idx);
                NewTracePixels(idx).superPixelNumPixels = superPixelNumPixels(idx);
                NewTracePixels(idx).superPixelNumPixelsSelected = validCounts(idx);
            end

            for lineIdx = 1:numel(obj.hMultiDataFiles.lineSuperPixelIDs)
                lineZIdx = obj.hMultiDataFiles.lineFastZIdxs(lineIdx);

                if lineZIdx ~= obj.zIdx
                    continue
                end

                lineSuperPixelIDs = obj.hMultiDataFiles.lineSuperPixelIDs{lineIdx};
                [mask,positions] = ismember(validSuperPixelIDs,lineSuperPixelIDs);
                
                byteOffsets = (positions(mask)-1) * 2;
                byteOffsets = byteOffsets + numel(lineSuperPixelIDs) * 2 * (obj.chIdx-1);
                byteOffsets = byteOffsets + obj.hMultiDataFiles.lineDataStartIdxs(lineIdx) * 2;
                byteOffsets = byteOffsets - obj.hMultiDataFiles.header.firstCycleOffsetBytes;
                
                pixIdxs = find(mask');
                
                for idx = 1:numel(pixIdxs)
                    pixIdx = pixIdxs(idx);
                    NewTracePixels(pixIdx).byteOffsets(end+1) = byteOffsets(idx);
                    NewTracePixels(pixIdx).lineIdxs(end+1) = lineIdx;
                end
            end

            TracePixels = [ExistingTracePixels;NewTracePixels];
            [~,idx] = sort([TracePixels.superPixelId]);
            TracePixels = TracePixels(idx);
        end
    end
end