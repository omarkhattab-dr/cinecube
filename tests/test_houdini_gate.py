"""the gate: a fake render that is the target x 0.37 flipped like an exr passes, a blurred one fails,
and the exporter writes what npz_to_vdb and the gate expect"""
import json
import os
import numpy as np
from scipy import ndimage

from cinecube.houdini.export_vdb import export_cube
from cinecube.houdini.gate import gate, write_exr, read_render

ROOT = os.path.join(os.path.dirname(__file__), "..")


def test_export_and_gate(tmp_path):
    vdb_dir = str(tmp_path / "vdb")
    meta = export_cube("l1448", os.path.join(ROOT, "data", "l1448_13co.fits"), vdb_dir, 1.0, 2.0)
    d = np.load(os.path.join(vdb_dir, "l1448.npz"))
    assert d["density"].shape == (53, 105, 105) and d["density"].min() >= 0
    assert meta["display_scale_K_kms"] > 0 and 0 <= meta["clip_cost_of_peak"] < 0.1
    target = np.load(os.path.join(vdb_dir, "l1448_target.npy"))
    assert np.allclose(target, d["density"].sum(axis=0) * meta["dv_kms"], rtol=1e-5)

    # a perfect emission render: the target times some karma scale, saved like an exr (row 0 at the top)
    exr = str(tmp_path / "plain.exr")
    write_exr(exr, (0.37 * target)[::-1])
    back = read_render(exr)
    assert back.shape == target.shape
    r = gate(exr, "l1448", vdb_dir, os.path.join(ROOT, "sweeps", "v1.yaml"), str(tmp_path / "out"), tol=0.01)
    assert r["passed"] and r["orientation"] == "flip rows" and abs(r["scale"] - 1 / 0.37) < 1e-3
    assert os.path.exists(tmp_path / "out" / "gate_l1448.json") and os.path.exists(tmp_path / "out" / "gate_l1448.png")

    # a blurred render (too big a step size) fails
    write_exr(exr, (0.37 * ndimage.gaussian_filter(target, 2.0))[::-1])
    r = gate(exr, "l1448", vdb_dir, os.path.join(ROOT, "sweeps", "v1.yaml"), str(tmp_path / "out"), tol=0.01)
    assert not r["passed"]
