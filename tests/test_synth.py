"""fake disk: builds, loads like a real cube, zero point holds on it too"""
import os
import numpy as np

from cinecube.synth import keplerian_disk, write_fits
from cinecube.io import load_cube, moment0
from cinecube.render import render
from cinecube.index import velocity_as_depth_index


def test_disk_builds_and_equivalence_holds(tmp_path):
    T, v, truth = keplerian_disk(nx=48, ny=48, nz=32, nv=24, noise_K=0.0)
    path = str(tmp_path / "disk.fits")
    write_fits(T, v, path, truth["params"]["dv"])
    cube = load_cube(path)
    m0 = moment0(cube)
    ref = render(cube.T, cube.dv)
    assert np.max(np.abs(ref - m0)) < 1e-6 * m0.max()
    # moment0 should be the column density, same shape same place
    col = truth["rho"].sum(axis=0)
    assert np.corrcoef(col.ravel(), m0.ravel())[0, 1] > 0.95


def test_index_is_zero_face_on():
    T, v, truth = keplerian_disk(nx=48, ny=48, nz=32, nv=24, noise_K=0.0)
    r0 = velocity_as_depth_index(T, truth["params"]["dv"], truth["rho"], 0.0, 1.0)
    r45 = velocity_as_depth_index(T, truth["params"]["dv"], truth["rho"], 45.0, 1.0)
    assert r0["one_minus_ssim"] < 0.05
    assert r45["one_minus_ssim"] > r0["one_minus_ssim"]


def test_safe_angle_crossing():
    from cinecube.index import safe_angle
    rows = [dict(theta=t, stretch=1, one_minus_ssim=v) for t, v in ((0, 0.0), (2, 0.008), (4, 0.016), (10, 0.07))]
    rows += [dict(theta=t, stretch=2, one_minus_ssim=v) for t, v in ((0, 0.0), (2, 0.02), (4, 0.04))]
    rows += [dict(theta=t, stretch=3, one_minus_ssim=v) for t, v in ((0, 0.0), (2, 0.001), (4, 0.002))]
    s = safe_angle(rows, 0.01)
    assert s["1"]["status"] == "value" and abs(s["1"]["theta"] - 2.5) < 1e-9     # crosses between 2 and 4, interpolated
    assert s["2"]["status"] == "value" and abs(s["2"]["theta"] - 1.0) < 1e-9
    assert s["3"]["status"] == "all" and s["3"]["theta"] == 4.0
