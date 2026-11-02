classdef MultiDataFiles < handle
    %MULTIDATAFILES Minimal test double accepted by Trace's concrete type.
    %
    % This class intentionally implements only the metadata surface read by
    % slap2.util.datafile.trace.Trace.

    properties
        header = struct( ...
            'dmdPixelsPerRow', 0, ...
            'dmdPixelsPerColumn', 0, ...
            'bytesPerCycle', 0, ...
            'firstCycleOffsetBytes', 0, ...
            'linesPerCycle', 0)
        zPixelReplacementMaps = {}
        hDataFiles = struct('filename', {})
        lineSuperPixelIDs = {}
        lineFastZIdxs = []
        lineDataStartIdxs = []
        metaData = struct()
        fastZs = []
    end

    methods
        function obj = MultiDataFiles(values)
            if nargin == 0
                return
            end

            if ischar(values) || (isstring(values) && isscalar(values))
                obj.configureVoltageFixture(char(values));
                return
            end

            names = fieldnames(values);
            for idx = 1:numel(names)
                obj.(names{idx}) = values.(names{idx});
            end
        end
    end

    methods (Access = private)
        function configureVoltageFixture(obj, filename)
            if exist(filename, 'file') ~= 2
                error('FakeMultiDataFiles:FileNotFound', ...
                    'Fake raw data file does not exist: %s', filename);
            end

            roi = struct('mask', logical([1 0; 0 0]), ...
                'imagingMode', 'test-double');
            obj.metaData = struct( ...
                'dmdPixelsPerRow', 2, ...
                'dmdPixelsPerColumn', 2, ...
                'samplesPerLine', 1, ...
                'channelsSave', 1, ...
                'linePeriod_s', 0.001, ...
                'AcquisitionContainer', struct( ...
                    'ROIs', struct('rois', {{roi}}), ...
                    'ParsePlan', struct('lineRateHz', 1000, 'zs', 12.5)));
            obj.fastZs = 12.5;
            obj.header = struct( ...
                'dmdPixelsPerRow', 2, ...
                'dmdPixelsPerColumn', 2, ...
                'bytesPerCycle', 16, ...
                'firstCycleOffsetBytes', 0, ...
                'linesPerCycle', 8);
            obj.lineSuperPixelIDs = repmat({uint32(5)}, 1, 8);
            obj.lineFastZIdxs = ones(1, 8);
            obj.lineDataStartIdxs = 0:7;
            obj.hDataFiles = struct('filename', filename);

            if contains(filename, 'no_voltage', 'IgnoreCase', true)
                obj.zPixelReplacementMaps = {uint32([0 1])};
            else
                obj.zPixelReplacementMaps = {uint32([0 5])};
            end
        end
    end
end
