function trialTable = buildTrialTableSLAP2(dr,savedr,useAllFiles)
%BUILDTRIALTABLESLAP2 Controllable unit-test double for processVoltage.

global PROCESS_VOLTAGE_BUILD_DOUBLE
PROCESS_VOLTAGE_BUILD_DOUBLE.calls{end+1} = struct( ...
    'dr',dr,'savedr',savedr,'useAllFiles',useAllFiles);

switch PROCESS_VOLTAGE_BUILD_DOUBLE.mode
    case 'empty'
        trialTable = [];
        return
    case 'missing-file'
        trialTable = validTrialTable(dr,savedr);
        return
    case 'incomplete'
        trialTable = struct('datadr',dr);
    otherwise
        trialTable = validTrialTable(dr,savedr);
end

fid = fopen(fullfile(savedr,'trial_table.h5'),'w');
if fid < 0
    error('ProcessVoltageTestDouble:CreateFailed', ...
        'Could not create trial_table.h5 in %s.',savedr);
end
fclose(fid);
end

function trialTable = validTrialTable(dr,savedr)
trialTable = struct( ...
    'datadr',dr, ...
    'savedr',savedr, ...
    'filename',{{'fixture.dat'}}, ...
    'true_trial_ix',1, ...
    'epoch',1, ...
    'slap2_info',struct('first_line',1,'last_line',1));
end
