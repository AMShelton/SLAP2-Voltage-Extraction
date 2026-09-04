function tests = test_trial_table_roundtrip
tests = functiontests(localfunctions);
end

function testRoundTrip(testCase)
root = fileparts(fileparts(mfilename('fullpath')));
addpath(fullfile(root,'dependencies','io'));
fn = [tempname '.h5'];
cleanup = onCleanup(@()deleteIfExists(fn)); %#ok<NASGU>
s = struct();
s.datadr = 'C:\data';
s.savedr = 'C:\out';
s.filename = {'a.dat','b.dat';'c.dat','d.dat'};
s.epoch = [1 1;1 1];
s.slap2_info = struct('first_line',[1 11;1 11], ...
    'last_line',[10 20;10 20], 'line_range_convention','inclusive');
saveStructToH5(s,fn);
r = loadStructFromH5(fn);
verifyEqual(testCase,r.filename,s.filename);
verifyEqual(testCase,double(r.slap2_info.first_line),double(s.slap2_info.first_line));
verifyEqual(testCase,char(r.slap2_info.line_range_convention),'inclusive');
end

function deleteIfExists(fn)
if exist(fn,'file'), delete(fn); end
end
