classdef TracePixel
    properties
        fileNames             (1,:) string = "";
        superPixelId          (1,1) double = 0;
        superPixelNumPixels   (1,1) single = 0;
        superPixelNumPixelsSelected (1,1) single = 0;
        byteOffsets           (1,:) uint32
        lineIdxs              (1,:) uint32
        data                        single
        isLoaded              (1,1) logical = false;
        firstCycleOffsetBytes (1,1) double = 0;
        bytesPerCycle         (1,1) double = 0;
        linesPerCycle         (1,1) double = 0;
    end

    methods
        function obj = loadSingleObject(obj,files)
            if obj.isLoaded
                return
            end

            obj.data = [];            

            for idx = 1:numel(obj.fileNames)
                file = files(obj.fileNames(idx));

                numCyclesInFile = floor((file.fileSizeBytes - obj.firstCycleOffsetBytes) / obj.bytesPerCycle);
                cycleIdxs = uint64(0:(numCyclesInFile-1));

                cycleByteOffsets = obj.firstCycleOffsetBytes + cycleIdxs * obj.bytesPerCycle;
                cycleSampleOffsets = cycleByteOffsets/2;

                sampleOffsets = obj.byteOffsets/2;
                sampleOffsets = uint64(sampleOffsets(:)) + cycleSampleOffsets(:)'; % using uint64 to index into memorymap should allow us to handle huge files
                data_ = file.memmap.Data(sampleOffsets);
                data_ = reshape(data_,size(sampleOffsets)); % memmaps will return a column vector if a row vector is given

                data_(data_ == intmin('int16')) = 0;
                obj.data = horzcat(obj.data,single(data_));
            end

            obj.isLoaded = true;
        end

        function objs = load(objs)
            arguments
                objs
            end

            needsLoading = ~[objs.isLoaded];
            if ~any(needsLoading)
                return;
            end

            fileNames_ = unique([objs(needsLoading).fileNames]);

            files = dictionary();
            for fileName = fileNames_
                s = struct();
                s.memmap = memmapfile(fileName, 'Format', 'int16');
                s.fileSizeBytes = numel(s.memmap.Data) * 2;

                files(fileName) = s;
            end

            for idx = 1:numel(objs)
                objs(idx) = objs(idx).loadSingleObject(files);
            end
        end

        function [objs,trace,sumDataWeighted,sumExpected,sumExpectedWeighted] = process(objs,windowWidth_lines,expectedWindowWidth_lines)
            % Memory-lean: load, use and release one superpixel at a time
            % (previously all superpixels' data were held in memory at once).
            tempKernel = exp(-abs((-4*windowWidth_lines) : (4*windowWidth_lines))./windowWidth_lines); %time weighting kernel
            tempKernel = single(tempKernel(:));

            expectedKernel = ones(expectedWindowWidth_lines,1,'single');

            sumDataWeighted     = zeros(0,1,'single');
            sumExpected         = zeros(0,1,'single');
            sumExpectedWeighted = zeros(0,1,'single');

            for idx = 1:numel(objs)
                objs(idx) = objs(idx).load();
                obj = objs(idx);

                numCycles = size(obj.data,2);
                if idx == 1
                    numLines = obj.linesPerCycle*numCycles;
                    sumDataWeighted     = zeros(numLines,1,'single');
                    sumExpected         = zeros(numLines,1,'single');
                    sumExpectedWeighted = zeros(numLines,1,'single');
                end
                spatialWeight = obj.superPixelNumPixelsSelected/obj.superPixelNumPixels;
                lineIdxs = obj.lineIdxs;
                linesPerCycle = obj.linesPerCycle;

                % Build the dense line-data vector, then free the loaded data
                % immediately (both the copy in objs and the local copy).
                lineData = zeros(linesPerCycle,numCycles,'single');
                lineData(lineIdxs,:) = obj.data;
                lineData = lineData(:);
                obj.data = single([]); %#ok<NASGU>
                objs(idx).data = single([]);
                objs(idx).isLoaded = false;
                clear obj

                % Data-dependent terms first, so the dense data vector can be
                % freed before the sampling-mask terms are computed.
                weightedData = conv(lineData,tempKernel .* spatialWeight,'same');
                sumDataWeighted = sumDataWeighted + weightedData;
                clear weightedData
                expected = conv(lineData,expectedKernel,'same');
                clear lineData

                sampled = zeros(linesPerCycle,numCycles,'single');
                sampled(lineIdxs,:) = 1;
                sampled = sampled(:);

                expectedN = conv(sampled,expectedKernel,'same');
                expected  = expected ./ (expectedN + eps('like',expectedN));
                clear expectedN

                tempWeights = conv(sampled,tempKernel,'same');
                clear sampled
                sumExpected         = sumExpected         + expected;
                sumExpectedWeighted = sumExpectedWeighted + expected .* tempWeights;
                clear expected tempWeights
            end

            trace = sumDataWeighted ./ (sumExpectedWeighted+eps('like',sumExpectedWeighted)) .* sumExpected;
        end

        function hFuture = processAsync(objs,windowWidth_lines,expectedWindowWidth_lines)
            % Voltage configures the MATLAB process pool before calling this
            % method. Reuse that pool directly rather than depending on the
            % ScanImage/MOST ParallelPoolManager utility.
            hPool = gcp('nocreate');
            if isempty(hPool)
                hPool = parpool;
            end
            numWorkers = hPool.NumWorkers;
            
            hFutures = parallel.FevalFuture.empty();
            N = ceil(numel(objs)/numWorkers);
            
            idxs = 1:N;
            while true
                idxs(idxs>numel(objs)) = [];
                if isempty(idxs)
                    break;
                end
                % Use a worker-side wrapper that drops loaded pixel data before
                % returning. Otherwise every worker serializes its full
                % [pixels x cycles] data matrices back to the client, which
                % causes "Out of Memory during serialization" on long recordings.
                hFutures(end+1) = parfeval(@processNoData,5,objs(idxs),windowWidth_lines,expectedWindowWidth_lines);
                idxs = idxs + N;
            end

            hFuture = hFutures.afterAll(@finalize,3,'PassFuture',true);

            %%% Nested function
            function [objs,trace, sumDataWeighted,sumExpected,sumExpectedWeighted] = finalize(hFutures)
                objs = slap2.util.datafile.trace.TracePixel.empty();
                sumDataWeighted     = [];
                sumExpected         = [];
                sumExpectedWeighted = [];

                for idx = 1:numel(hFutures)
                    [objs_,~,sumDataWeighted_,sumExpected_,sumExpectedWeighted_] = hFutures(idx).fetchOutputs();

                    objs = vertcat(objs,objs_);

                    if isempty(sumDataWeighted)
                        sumDataWeighted     = sumDataWeighted_;
                        sumExpected         = sumExpected_;
                        sumExpectedWeighted = sumExpectedWeighted_;
                    else
                        sumDataWeighted     = sumDataWeighted + sumDataWeighted_;
                        sumExpected         = sumExpected + sumExpected_;
                        sumExpectedWeighted = sumExpectedWeighted + sumExpectedWeighted_;
                    end
                end

                trace = sumDataWeighted ./ (sumExpectedWeighted+eps('like',sumExpectedWeighted)) .* sumExpected;
            end
        end
    end
end

function [objs,trace,sumDataWeighted,sumExpected,sumExpectedWeighted] = processNoData(objs,windowWidth_lines,expectedWindowWidth_lines)
%PROCESSNODATA Run TracePixel.process on a worker, returning objs without loaded data.
[objs,trace,sumDataWeighted,sumExpected,sumExpectedWeighted] = ...
    objs.process(windowWidth_lines,expectedWindowWidth_lines);
for k = 1:numel(objs)
    objs(k).data = single([]);
    objs(k).isLoaded = false;
end
end