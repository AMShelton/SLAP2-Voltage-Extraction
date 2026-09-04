function tests = test_computeVoltageDFF
tests = functiontests(localfunctions);
end

function testASAP8(testCase)
raw = single([100 110 90]);
f0 = single([100 100 100]);
[dff,meta] = computeVoltageDFF(raw,f0,'ASAP8','auto','single');
verifyEqual(testCase,dff,single([0 0.1 -0.1]),'AbsTol',single(1e-6));
verifyEqual(testCase,meta.dffSign,1);
end

function testASAP7(testCase)
raw = single([100 90 110]);
f0 = single([100 100 100]);
[dff,meta] = computeVoltageDFF(raw,f0,'ASAP7y','auto','single');
verifyEqual(testCase,dff,single([0 0.1 -0.1]),'AbsTol',single(1e-6));
verifyEqual(testCase,meta.dffSign,-1);
end

function testUnknownAutoFails(testCase)
verifyError(testCase,@()computeVoltageDFF(single(1),single(1),'unknown','auto','single'), ...
    'computeVoltageDFF:UnknownIndicatorDirection');
end
