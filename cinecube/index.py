"""
index.py - the velocity-as-depth index

2 worlds, same camera. world A = the ppv cube, what an orbiting camera shows you, v axis scaled
by the stretch. world B = the true density on its spatial grid. render both from the same angle
with the plain renderer and compare the 2 pictures. at theta 0 they are the same sky image so
the index is 0 by construction, then it grows with angle. biggest angle where it stays inside
the conditional band = the safe envelope.

    python -m cinecube.index --disk data/synthetic_disk.fits --truth data/synthetic_disk_truth.npz \
        --thetas 0 10 20 30 45 60 90 --stretch 1 2 3 --out results/v1/index_inc45.json

2 parts, both saved, keep whichever the paper needs:
    one_minus_ssim   1 - ssim between the 2 display normalized renders on a common canvas
    chamfer          mean symmetric chamfer distance (px) between the 2 silhouettes (> 10% of max)
"""
import argparse
import json

import numpy as np
from scipy import ndimage
from skimage.metrics import structural_similarity

from .io import load_cube
from .render import render, norm_disp


def _canvas(a, b):
    side = max(a.shape + b.shape)
    out = []
    for img in (a, b):
        c = np.zeros((side, side))
        y0 = (side - img.shape[0]) // 2
        x0 = (side - img.shape[1]) // 2
        c[y0:y0 + img.shape[0], x0:x0 + img.shape[1]] = img
        out.append(c)
    return out


def chamfer(mask_a, mask_b):
    if mask_a.sum() == 0 or mask_b.sum() == 0:
        return float("nan")
    da = ndimage.distance_transform_edt(~mask_a)
    db = ndimage.distance_transform_edt(~mask_b)
    return float(0.5 * (da[mask_b].mean() + db[mask_a].mean()))


def velocity_as_depth_index(T, dv, rho, theta_deg, stretch=1.0, sil_thresh=0.1):
    """one orbit setting -> dict(one_minus_ssim, chamfer, theta, stretch)"""
    ppv = render(T, dv, theta_deg=theta_deg, aspect=stretch)          # world A, v as depth
    true = render(rho, 1.0, theta_deg=theta_deg, aspect=1.0)           # world B, z as depth (px)
    a, b = _canvas(norm_disp(ppv), norm_disp(true))
    ssim = float(structural_similarity(a, b, data_range=1.0, win_size=7))
    ch = chamfer(a > sil_thresh, b > sil_thresh)
    return dict(theta=float(theta_deg), stretch=float(stretch), one_minus_ssim=1.0 - ssim, ssim=ssim, chamfer=ch)


def run(disk_path, truth_path, thetas, stretches, out):
    cube = load_cube(disk_path, name="disk")
    tr = np.load(truth_path, allow_pickle=False)
    rho = tr["rho"].astype(np.float64)
    params = json.loads(str(tr["params"]))
    # index is about geometry so use the clean cube when the truth has it.
    # noise just drags ssim down everywhere and hides the angle dependence
    T = tr["T_clean"].astype(np.float64) if "T_clean" in tr.files else cube.T
    rows = []
    for s in stretches:
        for th in thetas:
            r = velocity_as_depth_index(T, cube.dv, rho, th, s)
            rows.append(r)
            print("  stretch %gx  theta %3g  1-SSIM %.3f  chamfer %.2f px" % (s, th, r["one_minus_ssim"], r["chamfer"]))
    result = dict(disk=disk_path, truth=truth_path, inc_deg=params.get("inc_deg"), params=params, used_clean_cube=bool("T_clean" in tr.files), rows=rows)
    json.dump(result, open(out, "w"), indent=1)
    print("wrote", out)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="velocity-as-depth index on the synthetic disk")
    ap.add_argument("--disk", default="data/synthetic_disk.fits")
    ap.add_argument("--truth", default="data/synthetic_disk_truth.npz")
    ap.add_argument("--thetas", type=float, nargs="+", default=[0, 10, 20, 30, 45, 60, 90])
    ap.add_argument("--stretch", type=float, nargs="+", default=[1, 2, 3])
    ap.add_argument("--out", default="results/v1/index.json")
    a = ap.parse_args(argv)
    run(a.disk, a.truth, a.thetas, a.stretch, a.out)


if __name__ == "__main__":
    main()
