function tests = test_motion_censor
tests = functiontests(localfunctions);
end

function p = baseParams()
p = motionCensorDefaults();
p.motionCensorEnable = true;
end

function testDefaultsValidate(testCase)
p = validateMotionCensorParams(struct());
verifyFalse(testCase,p.motionCensorEnable);
verifyEqual(testCase,p.motionPixelSize_um,0.25);
verifyEqual(testCase,p.motionThresh,2.5);
end

function testSetParamsExposesMotionFields(testCase)
p = setParams('Voltage',struct());
names = fieldnames(motionCensorDefaults());
for k = 1:numel(names)
    verifyTrue(testCase,isfield(p,names{k}),names{k});
end
verifyFalse(testCase,p.motionCensorEnable);
end

function testStationaryNothingCensored(testCase)
mask = computeMotionCensor(zeros(1000,1),zeros(1000,1),50,baseParams());
verifyFalse(testCase,any(mask));
end

function testConstantOffsetIsDriftNotMotion(testCase)
% A large but constant offset is handled by online correction: no censoring.
mask = computeMotionCensor(8*ones(1000,1),-6*ones(1000,1),50,baseParams());
verifyFalse(testCase,any(mask));
end

function testJumpIsCensoredAndPadded(testCase)
x = zeros(1000,1); y = zeros(1000,1);
x(500:504) = 12;                       % 3 um excursion for 5 samples
x([498 499 505 506]) = 2;              % 0.5 um shoulders: above thresh/2, below thresh
p = baseParams(); p.motionPad_s = 0;   p.motionMergeGap_s = 0;
mask = computeMotionCensor(x,y,50,p);
verifyEqual(testCase,find(mask)',500:504);

% GIAnT semantics: padding only extends into shoulder samples above thresh/2.
p.motionPad_s = 0.04;                  % 2 samples each side at 50 Hz
maskPad = computeMotionCensor(x,y,50,p);
verifyEqual(testCase,find(maskPad)',498:506);
end

function testNearbySpansMerge(testCase)
x = zeros(1000,1); y = zeros(1000,1);
x(500:502) = 12; x(505:507) = 12;      % two excursions, 2-sample gap
p = baseParams(); p.motionPad_s = 0;   p.motionMergeGap_s = 0.1;
mask = computeMotionCensor(x,y,50,p);
verifyTrue(testCase,all(mask(500:507)));
end

function testAbsoluteCap(testCase)
x = 20*ones(1000,1); y = zeros(1000,1); % constant 5 um offset
p = baseParams(); p.motionAbsMax_um = 3;
mask = computeMotionCensor(x,y,50,p);
verifyTrue(testCase,all(mask));
end

function testNonFiniteOffsetsCensored(testCase)
x = zeros(200,1); y = zeros(200,1); x(50) = NaN;
mask = computeMotionCensor(x,y,50,baseParams());
verifyTrue(testCase,mask(50));
end

function testDiscardInitial(testCase)
p = baseParams(); p.motionDiscardInitial_s = 1;
mask = computeMotionCensor(zeros(500,1),zeros(500,1),50,p);
verifyTrue(testCase,all(mask(1:50)));
verifyFalse(testCase,any(mask(51:end)));
end

function testExpandMaskToLines(testCase)
% 3 cycles of 4 lines, first line of each cycle sampled.
lineIds = [1;5;9];
lineMask = expandMotionMaskToLines([false;true;false],lineIds,12);
verifyEqual(testCase,lineMask,logical([0 0 0 0 1 1 1 1 0 0 0 0]'));
% sampling a later line: leading lines take the first sample.
lineMask = expandMotionMaskToLines([true;false],[3;7],8);
verifyEqual(testCase,lineMask,logical([1 1 1 1 1 1 0 0]'));
end

function testExpandRejectsBadIds(testCase)
verifyError(testCase,@() expandMotionMaskToLines([true;false],[5;3],8), ...
    'expandMotionMaskToLines:InvalidLineIds');
end

function testCensoredSamplesDoNotBiasF0(testCase)
% Censored spans are NaN before F0: baseline stays at the clean level.
rng(1);
fs = 100; n = 6000;
raw = single(100 + 0.5*randn(n,1));
censor = false(n,1); censor(2000:2600) = true;
raw(censor) = single(300);                    % motion artifact
params = setParams('Voltage',struct('f0Method','robust','f0Bin_s',1,'f0Smooth_s',3));
rawMasked = raw; rawMasked(censor) = NaN;
f0Unmasked = computeVoltageF0(raw,fs,params);
verifyGreaterThan(testCase,max(f0Unmasked),150);   % the artifact does bias F0 if not masked
f0 = computeVoltageF0(rawMasked,fs,params);
verifyTrue(testCase,all(isfinite(f0)));
verifyLessThan(testCase,max(abs(f0-100)),2);
dff = computeVoltageDFF(rawMasked,f0,'ASAP8','increases','single');
verifyTrue(testCase,all(isnan(dff(censor))));
verifyTrue(testCase,all(isfinite(dff(~censor))));
end

function testAllCensoredEpochIsSafe(testCase)
params = setParams('Voltage',struct('f0Method','robust','f0Bin_s',1,'f0Smooth_s',3));
raw = nan(1000,1,'single');
f0 = computeVoltageF0(raw,100,params);
verifyTrue(testCase,all(isfinite(f0)));
end

function testEngineWiresMotionCensoring(testCase)
root = fileparts(fileparts(mfilename('fullpath')));
for name = {'Voltage.m','processVoltage.m'}
    txt = fileread(fullfile(root,name{1}));
    verifyTrue(testCase,contains(txt,'computeSourceMotionMask('),name{1});
    verifyTrue(testCase,contains(txt,'frame_info/motion_censor'),name{1});
    verifyTrue(testCase,contains(txt,'writeMotionMaskSlices('),name{1});
    verifyTrue(testCase,contains(txt,"fullfile(root,'dependencies','slap2_motion')"),name{1});
end
end
