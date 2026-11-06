"""
npz_to_vdb.py - runs INSIDE hython. npz from export_vdb.py -> .vdb with houdinis own volume tools.
no openvdb python bindings needed, houdini has vdb built in.

    hython cinecube/houdini/npz_to_vdb.py results/houdini/vdb/l1448.npz
    hython cinecube/houdini/npz_to_vdb.py results/houdini/vdb/*.npz          # all of them

what it does: hou.Geometry.createVolume(nx, ny, nz) with a bounding box so every voxel is
1 x 1 x stretch units, setAllVoxels with the density (x fastest, then y, then z, which is exactly
numpy C order of a [z, y, x] array), name attribute "density", then a Convert VDB sop turns the
houdini volume into a vdb and saveToFile writes it. the json next to the npz carries the metadata
(dv, scale, hash) because houdini volumes dont keep arbitrary metadata the way vdb grids do.

check in the viewport after: File sop -> the vdb. l1448 should be a 105 x 105 x 53 box with the
filament running diagonally, j1615 a 256 x 256 x 128 box with the disk in the middle.
"""
import json
import os
import sys

import numpy as np

try:
    import hou
except ImportError:
    sys.exit("this runs inside hython (or the houdini python shell), not plain python")


def npz_to_vdb(npz_path, out_path=None):
    d = np.load(npz_path, allow_pickle=False)
    den = d["density"].astype(np.float32)                 # [z, y, x]
    meta = json.loads(str(d["meta"])) if "meta" in d.files else {}
    nz, ny, nx = den.shape
    sx, sy, sz = meta.get("voxel_size_xyz", [1.0, 1.0, 1.0])
    name = meta.get("key", os.path.basename(npz_path).replace(".npz", ""))
    out_path = out_path or npz_path.replace(".npz", ".vdb")

    geo = hou.Geometry()
    bbox = hou.BoundingBox(0.0, 0.0, 0.0, nx * sx, ny * sy, nz * sz)   # voxel centres at i + 0.5, like the renderer
    vol = geo.createVolume(nx, ny, nz, bbox)
    vol.setAllVoxels(den.ravel().tolist())                 # x fastest, then y, then z
    geo.addAttrib(hou.attribType.Prim, "name", "")
    vol.setAttribValue("name", "density")

    # houdini volume -> vdb through a tiny sop network, then save
    tmp = out_path + ".tmp.bgeo.sc"
    geo.saveToFile(tmp)
    obj = hou.node("/obj").createNode("geo", "npz_to_vdb_" + name)
    f = obj.createNode("file"); f.parm("file").set(tmp)
    c = obj.createNode("convertvdb"); c.setInput(0, f)
    c.parm("conversion").set("vdb")
    c.geometry().saveToFile(out_path)
    obj.destroy()
    try:
        os.remove(tmp)
    except OSError:
        pass
    print("wrote %s  grid density %d x %d x %d voxels, voxel %g x %g x %g" % (out_path, nx, ny, nz, sx, sy, sz))
    return out_path


if __name__ == "__main__":
    paths = [p for p in sys.argv[1:] if p.endswith(".npz")]
    if not paths:
        sys.exit("usage: hython npz_to_vdb.py <file.npz> [more.npz ...]")
    for p in paths:
        npz_to_vdb(p)
