classdef Slap2DataFile
    %SLAP2DATAFILE Test double used by TestBuildTrialTableSLAP2.
    % The dummy DAT file contains only a decimal total-line count.

    properties
        totalNumLines
        hDataFile
    end

    methods
        function obj = Slap2DataFile(filename)
            text = strtrim(fileread(filename));
            nLines = str2double(text);
            if ~isscalar(nLines) || ~isfinite(nLines) || nLines < 0
                error('FakeSlap2DataFile:InvalidLineCount', ...
                    'Dummy DAT file must contain one finite nonnegative line count: %s', ...
                    filename);
            end

            obj.totalNumLines = nLines;
            obj.hDataFile = struct('metaData', struct('linePeriod_s', 1e-4));
        end
    end
end