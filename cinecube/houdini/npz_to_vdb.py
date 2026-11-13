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
    den = d["density"].astype(np.float32)
    meta = json.loads(str(d["meta"])) if "meta" in d.files else {}
    nz, ny, nx = den.shape
    sx, sy, sz = meta.get("voxel_size_xyz", [1.0, 1.0, 1.0])
    name = meta.get("key", os.path.basename(npz_path).replace(".npz", ""))
    out_path = out_path or npz_path.replace(".npz", ".vdb")

    geo = hou.Geometry()
    bbox = hou.BoundingBox(0.0, 0.0, 0.0, nx * sx, ny * sy, nz * sz)
    vol = geo.createVolume(nx, ny, nz, bbox)
    vol.setAllVoxels(den.ravel().tolist())
    geo.addAttrib(hou.attribType.Prim, "name", "")
    vol.setAttribValue("name", "density")

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
    import glob
    paths = [q for p in sys.argv[1:] for q in (sorted(glob.glob(p)) or [p]) if q.endswith(".npz")]
    if not paths:
        sys.exit("usage: hython npz_to_vdb.py <file.npz> [more.npz ...]")
    for p in paths:
        npz_to_vdb(p)
