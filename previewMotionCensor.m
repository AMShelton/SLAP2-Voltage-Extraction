function [params, info] = previewMotionCensor(dataFile, paramsIn, showGUI)
%PREVIEWMOTIONCENSOR Tune motion-censoring parameters before processVoltage.
%
%   [params, info] = previewMotionCensor()               pick a .dat file
%   [params, info] = previewMotionCensor(dataFile)       first CYCLE .dat of a source
%   [params, info] = previewMotionCensor(dataFile, paramsIn, showGUI)
%
% Reads only the online motion offsets (SLAP2 line headers); no fluorescence
% traces are extracted, so it is fast. It plots the xy offset magnitude, the
% drift-removed deviation with the censoring threshold, and the resulting mask,
% and reports the percent censored. With showGUI (default true) you can adjust
% the motion* parameters in optionsGUI and re-plot until you accept.
%
% The returned params contain only the motion* fields (motionCensorEnable is
% set true) and can be passed straight to processVoltage:
%
%   p = previewMotionCensor(datFile);
%   processVoltage(dr, savedr, false, p);

if nargin < 1 || isempty(dataFile)
    [fn, dr] = uigetfile({'*.dat','SLAP2 data (*.dat)'},'Select a SLAP2 CYCLE .dat file');
    if isequal(fn,0)
        error('previewMotionCensor:Cancelled','No data file selected.');
    end
    dataFile = fullfile(dr,fn);
end
if nargin < 2 || isempty(paramsIn), paramsIn = struct(); end
if nargin < 3 || isempty(showGUI), showGUI = true; end

if isempty(which('computeMotionCensor')) || isempty(which('getOnlineMotion'))
    setup;
end
if isempty(which('slap2.util.MultiDataFiles'))
    error('previewMotionCensor:MissingSLAP2Reader', ...
        'Cannot resolve slap2.util.MultiDataFiles. Add the SLAP2 reader to the path.');
end

[defaults, tooltips] = motionCensorDefaults();
params = defaults;
inNames = fieldnames(paramsIn);
for k = 1:numel(inNames)
    if isfield(defaults,inNames{k})
        params.(inNames{k}) = paramsIn.(inNames{k});
    end
end
params.motionCensorEnable = true;
params = validateMotionCensorParams(params);

hMDF = slap2.util.MultiDataFiles(char(dataFile));
cleanup = onCleanup(@() delete(hMDF)); %#ok<NASGU>
lineRateHz = 1/double(hMDF.metaData.linePeriod_s);

fprintf('Reading online motion offsets from %s ...\n', dataFile);
motion = readSourceOnlineMotion(hMDF, params.motionSamplesPerCycle, lineRateHz);
fprintf('  %d cycles, %d lines/cycle, offsets at %.1f Hz\n', ...
    motion.numCycles, motion.linesPerCycle, motion.fsOffsets);

fig = [];
while true
    [mask, info] = computeMotionCensor(motion.x, motion.y, motion.fsOffsets, params);
    info.mask = mask;
    info.motion = motion;
    fig = plotPreview(fig, motion, mask, info, params);
    fprintf('  %.2f%% censored (scale %.2f um, threshold %.2f um)\n', ...
        100*info.fractionCensored, info.scale_um, info.threshold_um);
    if ~showGUI, break, end

    choice = questdlg(sprintf('%.2f%% of samples censored.', 100*info.fractionCensored), ...
        'Motion censoring', 'Adjust parameters', 'Accept', 'Accept');
    if ~strcmp(choice,'Adjust parameters'), break, end

    sub = rmfield(params,'motionCensorEnable');
    edited = optionsGUI(sub, rmfield(tooltips,'motionCensorEnable'), 'Motion censoring');
    if isempty(edited) || ~isstruct(edited), break, end
    edited.motionCensorEnable = true;
    edited = validateMotionCensorParams(edited);
    if edited.motionSamplesPerCycle ~= params.motionSamplesPerCycle
        motion = readSourceOnlineMotion(hMDF, edited.motionSamplesPerCycle, lineRateHz);
    end
    params = edited;
end
end


function fig = plotPreview(fig, motion, mask, info, params)
if isempty(fig) || ~isvalid(fig)
    fig = figure('Name','Motion censoring preview','Color','w');
end
clf(fig);
t = motion.sampleTimes_s;
xUm = params.motionPixelSize_um*motion.x;
yUm = params.motionPixelSize_um*motion.y;

ax1 = subplot(4,1,1,'Parent',fig); hold(ax1,'on');
plot(ax1,t,xUm,'DisplayName','x'); plot(ax1,t,yUm,'DisplayName','y');
ylabel(ax1,'online xy (\mum)'); legend(ax1,'show','Location','best');
title(ax1,sprintf('%.2f%% censored', 100*info.fractionCensored));

ax2 = subplot(4,1,2,'Parent',fig);
plot(ax2,t,motion.z); ylabel(ax2,'online z (\mum)');

ax3 = subplot(4,1,3,'Parent',fig); hold(ax3,'on');
plot(ax3,t,info.normalizedDeviation);
yline(ax3,params.motionThresh,'r');
yline(ax3,params.motionThresh/2,'r:');
ylabel(ax3,'normalized deviation');

ax4 = subplot(4,1,4,'Parent',fig); hold(ax4,'on');
plot(ax4,t,info.magnitude_um); plot(ax4,t,info.baseline_um,'k:');
if params.motionAbsMax_um > 0, yline(ax4,params.motionAbsMax_um,'r'); end
ylabel(ax4,'|xy| (\mum)'); xlabel(ax4,'time (s)');
shadeMask(ax4,t,mask);
linkaxes([ax1 ax2 ax3 ax4],'x');
drawnow;
end


function shadeMask(ax,t,mask)
mask = mask(:);
d = diff([false; mask; false]);
starts = find(d == 1);
stops = find(d == -1) - 1;
if isempty(starts), return, end
yl = ylim(ax);
dt = median(diff(t));
for k = 1:min(numel(starts),2000)
    t0 = t(starts(k)) - dt/2;
    t1 = t(stops(k)) + dt/2;
    patch(ax,[t0 t1 t1 t0],[yl(1) yl(1) yl(2) yl(2)],[1 0 0], ...
        'FaceAlpha',0.15,'EdgeColor','none','HandleVisibility','off');
end
ylim(ax,yl);
end
