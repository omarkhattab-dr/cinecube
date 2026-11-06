"""
index.py - the velocity-as-depth index, the safe angle, the honest camera path

2 worlds, same camera. world A = the ppv cube, what an orbiting camera shows you, v axis scaled
by the stretch. world B = the true density on its spatial grid. render both from the same angle
with the plain renderer and compare the 2 pictures. at theta 0 they are the same sky image so
the index is 0 by construction, then it grows with angle.

    python -m cinecube.index --disk data/synthetic_disk.fits --truth data/synthetic_disk_truth.npz \
        --out results/v1/index_inc45.json
    python -m cinecube.index --path results/v1/index_inc45.json --frames 240 --out results/v1/safe_path_inc45.json

2 parts, both saved, keep whichever the paper needs:
    one_minus_ssim   1 - ssim between the 2 display normalized renders on a common canvas
    chamfer          mean symmetric chamfer distance (px) between the 2 silhouettes (> 10% of max)

the safe angle per stretch = biggest theta where the index is still under a threshold (first crossing,
linear interpolation between grid points). 2 thresholds in the json:
    threshold_beam   1 - ssim(true render, true render blurred to 2x the beam). same "twice the beam"
                     rule as the bands, but in the indexs own currency (no decoder in the loop). headline
    threshold_band   1 - structure_conditional_min from the disks controls.json (the plan said this one).
                     its 0.63 on the disk because the reader + 2x beam wreck ssim on a smooth disk through
                     26 gray levels, and the index never gets above 0.4, so everything would be "safe".
                     kept in the json so the paper can say why its not the one used
"""
import argparse
import json
import os

import numpy as np
from scipy import ndimage
from skimage.metrics import structural_similarity

from .io import load_cube
from .render import render, norm_disp

THETAS = [0, 2, 4, 6, 8, 10, 15, 20, 30, 45, 60, 90]
STRETCHES = [1, 2, 3]
FWHM2SIGMA = 1.0 / 2.3548


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


def _ssim(a, b):
    return float(structural_similarity(a, b, data_range=1.0, gaussian_weights=True, sigma=1.5, use_sample_covariance=False))


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
    ssim = _ssim(a, b)
    ch = chamfer(a > sil_thresh, b > sil_thresh)
    return dict(theta=float(theta_deg), stretch=float(stretch), one_minus_ssim=1.0 - ssim, ssim=ssim, chamfer=ch)


def beam_threshold(rho, beam_fwhm_px):
    """what twice the beam costs the true density picture, in index units: 1 - ssim(true, blur(true))"""
    true = norm_disp(render(rho, 1.0))
    sigma = 2.0 * beam_fwhm_px * FWHM2SIGMA
    blurred = norm_disp(ndimage.gaussian_filter(render(rho, 1.0), sigma))
    return 1.0 - _ssim(true, blurred), sigma


def safe_angle(rows, threshold, key="one_minus_ssim"):
    """per stretch: biggest theta where the index is still <= threshold. first crossing, linear interp.
    -> {stretch: dict(theta, status)}  status = value / all (never crosses in the grid) / none"""
    out = {}
    for s in sorted(set(r["stretch"] for r in rows)):
        ser = sorted([r for r in rows if r["stretch"] == s], key=lambda r: r["theta"])
        th = [r["theta"] for r in ser]
        ix = [r[key] for r in ser]
        if ix[0] > threshold:
            out[str(int(s))] = dict(theta=0.0, status="none")
            continue
        k = next((i for i in range(1, len(ix)) if ix[i] > threshold), None)
        if k is None:
            out[str(int(s))] = dict(theta=float(th[-1]), status="all")
            continue
        # crossing between k-1 and k
        f = (threshold - ix[k - 1]) / (ix[k] - ix[k - 1] + 1e-12)
        out[str(int(s))] = dict(theta=float(th[k - 1] + f * (th[k] - th[k - 1])), status="value", grid_below=float(th[k - 1]), grid_above=float(th[k]))
    return out


def run(disk_path, truth_path, thetas, stretches, out, controls_path=None):
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
    thr_beam, sigma = beam_threshold(rho, params.get("beam_fwhm_px", 2.5))
    safe = dict(beam=safe_angle(rows, thr_beam))
    thresholds = dict(beam=thr_beam, beam_blur_sigma_px=sigma)
    if controls_path and os.path.exists(controls_path):
        b = json.load(open(controls_path))["bands"]
        thr_band = 1.0 - b["structure_conditional_min"]
        thresholds["band"] = thr_band
        safe["band"] = safe_angle(rows, thr_band)
    print("  threshold (2x beam on the true picture) %.3f -> safe angle %s" % (thr_beam, {k: round(v["theta"], 1) for k, v in safe["beam"].items()}))
    result = dict(disk=disk_path, truth=truth_path, inc_deg=params.get("inc_deg"), params=params, used_clean_cube=bool("T_clean" in tr.files),
                  rows=rows, thresholds=thresholds, safe_angle=safe)
    json.dump(result, open(out, "w"), indent=1)
    print("wrote", out)
    return result


def _ease(t):
    return 0.5 - 0.5 * np.cos(np.pi * t)


def safe_path(index_json, n_frames=240, out=None):
    """a camera path that stays inside the safe angle: first half at stretch 1 (0 -> safe -> 0),
    second half at stretch 2 (0 -> safe -> 0), eased. the index is rendered for every frame, not
    interpolated, so the gauge in the disclosure shot is the real number"""
    d = json.load(open(index_json))
    cube = load_cube(d["disk"], name="disk")
    tr = np.load(d["truth"], allow_pickle=False)
    rho = tr["rho"].astype(np.float64)
    T = tr["T_clean"].astype(np.float64) if "T_clean" in tr.files else cube.T
    safe = d["safe_angle"]["beam"]
    legs = [(1, safe.get("1", {}).get("theta", 0.0)), (2, safe.get("2", {}).get("theta", 0.0))]
    per_leg = n_frames // len(legs)
    frames = []
    for leg, (stretch, amax) in enumerate(legs):
        for i in range(per_leg):
            t = i / max(per_leg - 1, 1)
            theta = amax * _ease(2 * t if t < 0.5 else 2 - 2 * t)      # out and back
            r = velocity_as_depth_index(T, cube.dv, rho, theta, stretch)
            frames.append(dict(frame=len(frames), t=float(t), leg=leg, theta=float(theta), stretch=float(stretch), index=r["one_minus_ssim"]))
    worst = max(f["index"] for f in frames)
    result = dict(index_json=index_json, threshold=d["thresholds"]["beam"], safe_angle=safe, n_frames=len(frames), max_index_on_path=worst,
                  inside=bool(worst <= d["thresholds"]["beam"] + 1e-6), frames=frames)
    if out:
        json.dump(result, open(out, "w"), indent=1)
        print("wrote %s: %d frames, max index %.3f (threshold %.3f), inside: %s" % (out, len(frames), worst, d["thresholds"]["beam"], result["inside"]))
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="velocity-as-depth index on the synthetic disk, or the safe camera path from one")
    ap.add_argument("--disk", default="data/synthetic_disk.fits")
    ap.add_argument("--truth", default="data/synthetic_disk_truth.npz")
    ap.add_argument("--thetas", type=float, nargs="+", default=THETAS)
    ap.add_argument("--stretch", type=float, nargs="+", default=STRETCHES)
    ap.add_argument("--controls", default="results/v1/disk/controls.json", help="for the band threshold, optional")
    ap.add_argument("--out", default="results/v1/index.json")
    ap.add_argument("--path", default=None, help="an index json -> write the safe camera path instead")
    ap.add_argument("--frames", type=int, default=240)
    a = ap.parse_args(argv)
    if a.path:
        safe_path(a.path, a.frames, a.out)
    else:
        run(a.disk, a.truth, a.thetas, a.stretch, a.out, a.controls)


if __name__ == "__main__":
    main()
