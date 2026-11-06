"""
export_vdb.py - cube -> volume files for houdini

writes for every cube:
    <out>/<key>.npz        density [z, y, x] float32 in K (T clipped at 0), plus the axes and metadata
    <out>/<key>.json       everything houdini needs to know: shape, voxel size, dv, scale, hash, units
    <out>/<key>_target.npy the gate target: sum over z of the clipped density times dv
    <out>/<key>.vdb        only if the openvdb python bindings import (conda-forge), grid "density"
and for the fake disk also <out>/disk_truth.npz / .vdb with the true density on the sky grid (B7).

the npz is the carrier when there are no bindings: houdini/npz_to_vdb.py turns it into a vdb inside
hython with houdinis own volume tools. same grid, same metadata, so it doesnt matter which road.

    python -m cinecube.houdini.export_vdb --out results/houdini/vdb          # every cube in sweeps/v1.yaml
    python -m cinecube.houdini.export_vdb --cube l1448 --stretch 2

geometry: voxel (x, y, z) = (ra pixel, dec pixel, channel). x and y are 1 unit, z is `stretch` units
(1 = the sky field and the velocity axis get the same size per voxel, which is what the python orbit
operator does with aspect 1). the camera for the gate looks down -z at the whole x y field,
1 pixel per voxel, so the render lines up with the moment0 map without resampling.

the display scale in the json = the 99.8 pct of the plain render = K km/s at display 1.0. its what
the bridge needs to turn a houdini png back into physical units.
"""
import argparse
import json
import os

import numpy as np
import yaml

from ..io import load_cube, cube_hash
from ..render import render


def _vdb_module():
    for name in ("openvdb", "pyopenvdb"):
        try:
            return __import__(name)
        except ImportError:
            continue
    return None


def write_vdb(path, density, stretch=1.0, name="density", meta=None):
    """density [z, y, x] -> vdb float grid. needs the openvdb python bindings. returns False if not there"""
    vdb = _vdb_module()
    if vdb is None:
        return False
    grid = vdb.FloatGrid()
    grid.copyFromArray(np.ascontiguousarray(density.transpose(2, 1, 0).astype(np.float32)))   # (i, j, k) = (x, y, z)
    m = np.eye(4); m[2, 2] = stretch
    grid.transform = vdb.createLinearTransform(m.tolist())
    grid.name = name
    grid.gridClass = vdb.GridClass.FOG_VOLUME
    for k, v in (meta or {}).items():
        if isinstance(v, (int, float, str, bool)):
            grid[k] = v
    vdb.write(path, grids=[grid])
    return True


def export_cube(key, path, out, stretch=1.0, yaml_beam=None):
    cube = load_cube(path, name=key, beam_fwhm_px=yaml_beam)
    T = np.clip(cube.T, 0, None).astype(np.float32)
    ref = render(cube.T, cube.dv)                       # the real moment0 (noise negatives included)
    target = T.sum(axis=0) * cube.dv                    # what the vdb can give back: the clipped sum
    scale = float(np.percentile(ref, 99.8))
    from ..io import moment0, sky_mask
    mask = sky_mask(moment0(cube), cube.sigma_m0, 3.0, cube.valid)
    clip_cost = float(np.abs(target - ref)[mask].max() / ref.max())
    meta = dict(key=key, source=os.path.basename(path), cube_hash=cube_hash(path), shape_zyx=[int(s) for s in T.shape],
                voxel_size_xyz=[1.0, 1.0, float(stretch)], stretch=float(stretch), dv_kms=float(cube.dv),
                v_kms=[float(cube.v[0]), float(cube.v[-1])], unit="K", display_scale_K_kms=scale,
                moment0_max_K_kms=float(ref.max()), sigma_K=float(cube.sigma), beam_fwhm_px=cube.beam_fwhm_px,
                clip_cost_of_peak=clip_cost,
                note="density = T clipped at 0 in K (karma cant emit negative). sum over z of density * dv = the gate target "
                     "(<key>_target.npy), which differs from the real moment0 by the clipped noise: clip_cost_of_peak is the max of "
                     "that inside the sky mask, as a fraction of the map peak. camera for the gate looks down -z, ortho, 1 px per voxel")
    os.makedirs(out, exist_ok=True)
    np.savez_compressed(os.path.join(out, key + ".npz"), density=T, v=cube.v.astype(np.float32), meta=json.dumps(meta))
    np.save(os.path.join(out, key + "_target.npy"), target.astype(np.float32))
    json.dump(meta, open(os.path.join(out, key + ".json"), "w"), indent=1)
    got_vdb = write_vdb(os.path.join(out, key + ".vdb"), T, stretch, "density", meta)
    print("%-8s %s  scale %.2f K km/s  dv %.3f  clip cost %.4f of peak  -> npz + json + target%s" % (key, T.shape, scale, cube.dv, clip_cost, " + vdb" if got_vdb else " (no openvdb bindings here, run npz_to_vdb.py in hython)"))
    return meta


def export_truth(truth_path, out, key="disk_truth"):
    """the fake disks true 3d density on the sky grid, 2nd grid for the disclosure shot (B7)"""
    tr = np.load(truth_path, allow_pickle=False)
    rho = tr["rho"].astype(np.float32)                 # [z, y, x], z = line of sight in px
    params = json.loads(str(tr["params"]))
    meta = dict(key=key, source=os.path.basename(truth_path), shape_zyx=[int(s) for s in rho.shape], voxel_size_xyz=[1.0, 1.0, 1.0],
                stretch=1.0, unit="column density units, sum over z = moment0 of the disk", params=params,
                note="true density. same x y grid as disk.npz, z is real depth in pixels not velocity")
    np.savez_compressed(os.path.join(out, key + ".npz"), density=rho, meta=json.dumps(meta))
    json.dump(meta, open(os.path.join(out, key + ".json"), "w"), indent=1)
    got_vdb = write_vdb(os.path.join(out, key + ".vdb"), rho, 1.0, "density", meta)
    print("%-8s %s  (true density) -> npz + json%s" % (key, rho.shape, " + vdb" if got_vdb else ""))
    return meta


def main(argv=None):
    ap = argparse.ArgumentParser(description="export the cubes as volumes for houdini")
    ap.add_argument("--yaml", default="sweeps/v1.yaml")
    ap.add_argument("--cube", default=None, help="one key, default all")
    ap.add_argument("--out", default="results/houdini/vdb")
    ap.add_argument("--stretch", type=float, default=1.0, help="voxel size along the velocity axis")
    ap.add_argument("--truth", default="data/synthetic_disk_truth.npz")
    a = ap.parse_args(argv)
    cfg = yaml.safe_load(open(a.yaml))
    for key, path in cfg["cubes"].items():
        if a.cube and key != a.cube:
            continue
        if not os.path.exists(path):
            print("skip %s, %s missing (make disk?)" % (key, path)); continue
        yb = (cfg.get("beams") or {}).get(key)
        export_cube(key, path, a.out, a.stretch, float(yb) if yb else None)
    if (not a.cube or a.cube == "disk") and os.path.exists(a.truth):
        export_truth(a.truth, a.out)


if __name__ == "__main__":
    main()
