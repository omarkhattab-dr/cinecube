"""
sweep.py - run a yaml sweep, 1 png + 1 json per frame, then a scorecard

    python -m cinecube.sweep sweeps/v1.yaml                 # all cubes in the yaml
    python -m cinecube.sweep sweeps/v1.yaml --cube l1448    # just one

yaml looks like this (see sweeps/v1.yaml):
    cubes:
      l1448: data/l1448_13co.fits
    beams: {l1448: 2.0}      # beam fwhm in px per cube. yaml > fits header > controls.beam_fwhm_px
    noise_edge_channels: 3   # empty channels at each end of the band for the noise
    out: results/v1
    decoder: {mode: blind, recipe: jnd, jnd: 2.9}
    vis_jnd: 2.3
    controls: {beam_fwhm_px: 2.0}
    operators:
      - name: log
      - name: threshold
        grid: {k: [1, 2, 3, 5]}
      - name: orbit
        grid: {theta: [0, 10, 20, 30, 45, 60, 90], aspect: [1, 2, 3]}

every frame json has the operator, params, decoder settings, scores, cube hash and version,
so the scorecard can be rebuilt from the sidecars alone
"""
import argparse
import itertools
import json
import os
import sys
import time

import numpy as np
import yaml
from PIL import Image

from . import __version__
from .io import load_cube, moment0, sky_mask, cube_hash
from .render import render, norm_disp, center_crop_like
from .operators import apply_operator, OPERATORS
from .decode import decode_frame, zero_color_lab
from .metrics import score_frame, controls, bands_from_controls, classify, flip_score
from .operators import colormap


def expand(entry):
    """{name, grid: {a: [..], b: [..]}} -> list of (name, params)"""
    name = entry["name"]
    grid = entry.get("grid") or {}
    if not grid:
        return [(name, dict(entry.get("params") or {}))]
    keys = list(grid)
    out = []
    for combo in itertools.product(*[grid[k] for k in keys]):
        p = dict(entry.get("params") or {})
        p.update(dict(zip(keys, combo)))
        out.append((name, p))
    return out


def save_png(rgb, path):
    Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8)[::-1]).save(path)


def run_cube(cfg, key, path, out_root):
    t0 = time.time()
    yaml_beam = (cfg.get("beams") or {}).get(key)
    cube = load_cube(path, name=key, n_edge=cfg.get("noise_edge_channels", 3), beam_fwhm_px=float(yaml_beam) if yaml_beam else None)
    m0 = moment0(cube)
    ref = render(cube.T, cube.dv)
    ref01 = norm_disp(ref)
    mask = sky_mask(m0, cube.sigma_m0, cfg.get("mask_k", 3.0), cube.valid)
    out = os.path.join(out_root, key)
    os.makedirs(os.path.join(out, "frames"), exist_ok=True)
    dec = dict(cfg.get("decoder") or {})
    mode = dec.pop("mode", "blind")
    vis = cfg.get("vis_jnd", 2.3)
    chash = cube_hash(path)

    equiv = float(np.max(np.abs(ref - m0)))
    print("[%s] cube %s  dv %.4f km/s  sigma %.3f K  |ref - m0|max %.2e  mask %d px" % (key, cube.shape, cube.dv, cube.sigma, equiv, int(mask.sum())))
    if cube.meta.get("converted"):
        print("[%s] loader: %s, %s" % (key, cube.meta["converted"], cube.meta.get("spectral_in")))

    ctrl_cfg = cfg.get("controls") or {}
    # beam fwhm in px: yaml beams[key] wins (load_cube got it), then the fits header, then controls.beam_fwhm_px
    beam = float(cube.beam_fwhm_px or ctrl_cfg.get("beam_fwhm_px", 2.0))
    print("[%s] beam %.2f px (%s)" % (key, beam, "yaml" if yaml_beam else cube.meta.get("beam_source", "default")))
    ctrl = controls(m0, ref, mask, beam_fwhm_px=beam, decoder=dec, jnd_vis=vis)
    bands = bands_from_controls(ctrl)
    if cfg.get("bands"):
        # bands in the yaml override the derived ones (eg the oct 27 guess 0.95 / 0.80)
        bands.update(cfg["bands"])
        bands["source"] = "yaml"
    else:
        bands["source"] = "controls"
    json.dump(dict(controls=ctrl, bands=bands), open(os.path.join(out, "controls.json"), "w"), indent=1)
    print("[%s] bands: preserving >= %.3f, conditional >= %.3f (data recovered)" % (key, bands["preserving_min"], bands["conditional_min"]))

    rows = []
    jobs = [("reference", {})] + [job for e in cfg["operators"] for job in expand(e)]
    for i, (name, params) in enumerate(jobs):
        fr = apply_operator(cube, name, params)
        recovered, rec01 = decode_frame(fr, mode=mode, **dec)
        zero = zero_color_lab(fr["cmap"])      # blind viewer compares to the legend, not to the graded zero
        s = score_frame(m0, ref01, recovered, mask, fr["rgb"], zero, vis)
        s["flip"] = flip_score(colormap(ref01, "gray"), fr["rgb"]) if fr["rgb"].shape[:2] == ref01.shape else None
        row = dict(index=i, name=name, params=params, label=fr["label"], family=fr["family"], kind=fr["kind"], expected_class=fr["cls"],
                   cmap=fr["cmap"], decoder=dict(mode=mode, **dec), vis_jnd=vis, scores=s,
                   data_recovered=s["headline"]["data_recovered"], structure_kept=s["headline"]["structure_kept"], flux_visible=s["headline"]["flux_visible"],
                   band=classify(s["headline"]["data_recovered"], bands), cube=key, cube_hash=chash, version=__version__)
        # fair orbit comparison, same frame scored against the reference from the same camera
        if name == "orbit":
            cm = render(cube.T, cube.dv, theta_deg=params["theta"], aspect=params["aspect"])
            cm_c = center_crop_like(cm, ref) if cm.shape != ref.shape else cm
            s2 = score_frame(cm_c, norm_disp(cm_c), recovered, sky_mask(cm_c, cube.sigma_m0, 3.0, cube.valid if cm_c.shape == cube.valid.shape else None), fr["rgb"], zero, vis)
            row["camera_matched"] = s2["headline"]
        tag = "%03d_%s" % (i, name) + ("" if not params else "_" + "_".join("%s%s" % (k, v) for k, v in params.items()))
        tag = tag.replace(".", "p").replace(" ", "")
        save_png(fr["rgb"], os.path.join(out, "frames", tag + ".png"))
        json.dump(row, open(os.path.join(out, "frames", tag + ".json"), "w"), indent=1)
        rows.append(row)
        print("  %-36s data %.3f  structure %.3f  flux %.2f  %s" % (fr["label"], row["data_recovered"], row["structure_kept"], row["flux_visible"], row["band"]))

    card = dict(cube=key, path=path, cube_hash=chash, shape=list(cube.shape), dv=cube.dv, sigma=cube.sigma, equivalence_max_abs_diff=equiv,
                m0_max=float(m0.max()), mask_pixels=int(mask.sum()), decoder=dict(mode=mode, **dec), vis_jnd=vis, beam_fwhm_px=beam, cube_meta=cube.meta, bands=bands,
                controls=ctrl, rows=rows, version=__version__, seconds=round(time.time() - t0, 1))
    json.dump(card, open(os.path.join(out, "scorecard.json"), "w"), indent=1)
    print("[%s] %d frames in %.1f s -> %s" % (key, len(rows), card["seconds"], os.path.join(out, "scorecard.json")))
    return card


def main(argv=None):
    ap = argparse.ArgumentParser(description="run a cinecube sweep")
    ap.add_argument("yaml")
    ap.add_argument("--cube", help="only this cube key from the YAML")
    ap.add_argument("--out", help="override the output root")
    a = ap.parse_args(argv)
    cfg = yaml.safe_load(open(a.yaml))
    out_root = a.out or cfg.get("out", "results/v1")
    for key, path in cfg["cubes"].items():
        if a.cube and key != a.cube:
            continue
        run_cube(cfg, key, path, out_root)


if __name__ == "__main__":
    main()
