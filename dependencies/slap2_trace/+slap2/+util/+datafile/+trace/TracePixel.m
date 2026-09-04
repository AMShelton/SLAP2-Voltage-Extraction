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
            objs = objs.load();

            tempKernel = exp(-abs((-4*windowWidth_lines) : (4*windowWidth_lines))./windowWidth_lines); %time weighting kernel
            tempKernel = single(tempKernel(:));

            expectedKernel = ones(expectedWindowWidth_lines,1,'single');

            if isempty(objs)
                numLines = 0;
            else
                numCycles = size(objs(1).data,2);
                numLines = objs(1).linesPerCycle*numCycles;
            end

            sumDataWeighted     = zeros(numLines,1,'single');
            sumExpected         = zeros(numLines,1,'single');
            sumExpectedWeighted = zeros(numLines,1,'single');

            for idx = 1:numel(objs)
                obj = objs(idx);

                numCycles = size(obj.data,2);
                lineData = zeros(obj.linesPerCycle,numCycles,'single');
                sampled  = zeros(obj.linesPerCycle,numCycles,'single');

                lineData(obj.lineIdxs,:) = obj.data;
                sampled(obj.lineIdxs,:) = 1;

                lineData = lineData(:);
                sampled  = sampled(:);
                
                spatialWeight = obj.superPixelNumPixelsSelected/obj.superPixelNumPixels;
                weightedData  = conv(lineData,tempKernel .* spatialWeight,'same');
                tempWeights   = conv(sampled, tempKernel,'same');

                expected  = conv(lineData,expectedKernel,'same');
                expectedN = conv(sampled, expectedKernel,'same');
                expected  = expected ./ (expectedN + eps('like',expectedN));

                expectedWeighted = expected .* tempWeights;

                sumDataWeighted     = sumDataWeighted      + weightedData;
                sumExpected         = sumExpected          + expected;
                sumExpectedWeighted = sumExpectedWeighted  + expectedWeighted;      
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
                hFutures(end+1) = parfeval(@process,5,objs(idxs),windowWidth_lines,expectedWindowWidth_lines);
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