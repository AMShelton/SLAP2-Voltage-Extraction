function tests = test_repository_layout
tests = functiontests(localfunctions);
end

function testRequiredFiles(testCase)
root = fileparts(fileparts(mfilename('fullpath')));
required = { ...
    'Voltage.m', ...
    'buildTrialTableSLAP2.m', ...
    fullfile('source_extraction','computeVoltageF0.m'), ...
    fullfile('source_extraction','computeVoltageDFF.m'), ...
    fullfile('dependencies','io','loadStructFromH5.m'), ...
    fullfile('dependencies','io','saveStructToH5.m'), ...
    fullfile('dependencies','gui','setParams.m'), ...
    fullfile('dependencies','gui','optionsGUI.m'), ...
    fullfile('dependencies','slap2_trace','+slap2','+util','+datafile','+trace','Trace.m'), ...
    fullfile('dependencies','slap2_trace','+slap2','+util','+datafile','+trace','TracePixel.m')};
for k = 1:numel(required)
    verifyEqual(testCase,exist(fullfile(root,required{k}),'file'),2,required{k});
end
end

function testVendoredTracePackageResolves(testCase)
root = fileparts(fileparts(mfilename('fullpath')));
traceRoot = fullfile(root,'dependencies','slap2_trace');
oldPath = path;
cleanup = onCleanup(@() path(oldPath)); %#ok<NASGU>
addpath(traceRoot,'-begin');
verifyNotEmpty(testCase,which('slap2.util.datafile.trace.Trace'));
verifyNotEmpty(testCase,which('slap2.util.datafile.trace.TracePixel'));
end

function testTracePixelHasNoMostPoolDependency(testCase)
root = fileparts(fileparts(mfilename('fullpath')));
fn = fullfile(root,'dependencies','slap2_trace','+slap2','+util','+datafile','+trace','TracePixel.m');
txt = fileread(fn);
verifyFalse(testCase,contains(txt,'most.util.ParallelPoolManager'));
verifyTrue(testCase,contains(txt,"gcp('nocreate')"));
end

function testVoltageBootstrapsVendoredTrace(testCase)
root = fileparts(fileparts(mfilename('fullpath')));
txt = fileread(fullfile(root,'Voltage.m'));
verifyTrue(testCase,contains(txt,'bootstrapRepositoryPaths();'));
verifyTrue(testCase,contains(txt,fullfile('dependencies','slap2_trace')) || contains(txt,"'dependencies','slap2_trace'"));
verifyTrue(testCase,contains(txt,"format_version = '0.2.3'"));
end

function testVoltageCleansPartialOutputOnFailure(testCase)
root = fileparts(fileparts(mfilename('fullpath')));
txt = fileread(fullfile(root,'Voltage.m'));
verifyTrue(testCase,contains(txt,'cleanupPartialOutput(outputPath,ME)'));
verifyTrue(testCase,contains(txt,'Removed incomplete Voltage output after failure'));
end
