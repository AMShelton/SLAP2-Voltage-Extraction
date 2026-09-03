function tests = test_computeVoltageF0
tests = functiontests(localfunctions);
end

function testStaticConstant(testCase)
params = setParams('Voltage',struct('f0Method','static','f0Percentile',50,'precision','single'));
raw = single(5*ones(1,100));
[f0,meta] = computeVoltageF0(raw,1000,params);
verifyEqual(testCase,f0,single(5*ones(1,100)));
verifyFalse(testCase,meta.timeVarying);
end

function testRobustConstant(testCase)
params = setParams('Voltage',struct('f0Method','robust','f0Percentile',50, ...
    'f0Bin_s',1,'f0Smooth_s',3,'precision','single'));
raw = single(7*ones(1,1000));
[f0,meta] = computeVoltageF0(raw,100,params);
verifyEqual(testCase,f0,single(7*ones(1,1000)),'AbsTol',single(1e-6));
verifyTrue(testCase,meta.timeVarying);
end
