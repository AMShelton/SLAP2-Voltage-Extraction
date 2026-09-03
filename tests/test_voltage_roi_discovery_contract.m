function tests = test_voltage_roi_discovery_contract
tests = functiontests(localfunctions);
end

function testParsePlanClassificationNotImagingModeString(testCase)
root = fileparts(fileparts(mfilename('fullpath')));
src = fileread(fullfile(root,'Voltage.m'));

verifyNotEmpty(testCase, strfind(src, ...
    'hTrace.setPixelIdxs([],candidateMasks(:,:,i));')); %#ok<STRIFCND>
verifyEmpty(testCase, strfind(src, ...
    'strcmpi(char(mode),''Integrate'')')); %#ok<STRIFCND>
verifyNotEmpty(testCase, strfind(src, ...
    'parse_plan_integration_membership')); %#ok<STRIFCND>
end

function testRawExtractionKeepsLegacyMaskSemantics(testCase)
root = fileparts(fileparts(mfilename('fullpath')));
src = fileread(fullfile(root,'Voltage.m'));

% ROI classification uses integration-only mapping, but raw F must continue to
% select the ROI mask as both raster and integration pixels for legacy parity.
verifyNotEmpty(testCase, strfind(src, ...
    'hTrace.setPixelIdxs(mask,mask);')); %#ok<STRIFCND>
end

function testAllZeroRoisFailAndDeleteOutput(testCase)
root = fileparts(fileparts(mfilename('fullpath')));
src = fileread(fullfile(root,'Voltage.m'));

verifyNotEmpty(testCase, strfind(src,'totalVoltageRoisFound == 0')); %#ok<STRIFCND>
verifyNotEmpty(testCase, strfind(src,'Voltage:NoVoltageROIs')); %#ok<STRIFCND>
verifyNotEmpty(testCase, strfind(src,'delete(outputPath)')); %#ok<STRIFCND>
end

function testParallelPoolIsLazy(testCase)
root = fileparts(fileparts(mfilename('fullpath')));
src = fileread(fullfile(root,'Voltage.m'));

roiCheck = strfind(src,'if nRois == 0');
poolConfigure = strfind(src,'params = configureParallelPool(params);');
verifyNotEmpty(testCase,roiCheck);
verifyNotEmpty(testCase,poolConfigure);
verifyGreaterThan(testCase,poolConfigure(1),roiCheck(1));
end
