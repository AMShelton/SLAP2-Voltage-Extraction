function [data, meta, desc] = ScanImageTiffWrapper(fn)
%A = ScanImageTiffReader; data/meta/desc as from that reader (single open).
%   desc - cell array of ImageDescription strings per frame (IFF nargout>2)
A = ScanImageTiffReader(fn);
data = ScanImageTiffDataWrapper(A, fn);
meta = A.metadata();
if nargout > 2
    desc = A.descriptions();
end
A.close();
delete(A);

end