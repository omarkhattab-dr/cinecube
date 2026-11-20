"""touchdesigner sweep, python side. 3 steps:

    python -m cinecube.td.sweep_td specs  sweeps/td_v1.yaml     # -> results/td/specs.json (1 entry per frame)
    (in td)  exec(open(".../cinecube/td/td_scene.py").read()); build(); run_specs()   # -> results/td/<cube>/raw/*.npy
    python -m cinecube.td.sweep_td score  sweeps/td_v1.yaml     # -> results/td/<cube>/scorecard.json (track a's shape)
    python -m cinecube.td.sweep_td twins  sweeps/td_v1.yaml     # -> paper/figures/fig_twins_<cube>.png + results/td/twins.json

volume frames come back in K km/s and get track a's display (norm_disp, gray). post frames come back as float rgb
from td's own tops and are read with their legend (gray, or the colormap). same decoder, metrics and bands.
"""
import argparse
import itertools
import json
import os
import time

import numpy as np
import yaml

from .. import __version__
from ..io import load_cube, moment0, sky_mask, cube_hash
from ..render import render, norm_disp, disp_scale, center_crop_like
from ..operators import OPERATORS, apply_operator, colormap
from ..decode import decode_frame, zero_color_lab
from ..metrics import score_frame, controls, bands_from_controls, classify, flip_score
from ..sweep import save_png

PARAM_TO_KNOB = {"k": "k", "tau": "tau", "theta": "theta", "aspect": "stretch", "sigma": "dof", "strength": "light",
                 "step": "step", "cmap": "cmap", "gain": "bloom", "gamma": "gamma"}
POST_KNOB = {"grade_teal_orange": {"strength": "grade"}, "vignette": {"strength": "vignette"}, "grain": {"sigma": "grain"}}
TD_ONLY = {
    "light": dict(family="lighting", cls="hallucinator", label="TD light + self shadow {strength:g}"),
    "step": dict(family="sampling", cls="confuser", label="TD ray step {step:g} voxel"),
    "nearest": dict(family="sampling", cls="confuser", label="TD nearest voxel, step {step:g}"),
    "exposure": dict(family="color", cls="jumbler", label="TD level gamma {gamma:g}"),
}


def load_cfg(path):
    cfg = yaml.safe_load(open(path))
    base = yaml.safe_load(open(cfg["base"])) if cfg.get("base") else {}
    base.update({k: v for k, v in cfg.items() if k != "base"})
    return base


def expand(entry):
    grid = entry.get("grid") or {}
    keys = list(grid)
    combos = itertools.product(*[grid[k] for k in keys]) if keys else [()]
    for combo in combos:
        params = dict(zip(keys, combo))
        knobs = dict(entry.get("knobs") or {})
        for k, v in params.items():
            knobs[(POST_KNOB.get(entry["name"]) or {}).get(k) or PARAM_TO_KNOB[k]] = v
        yield params, knobs


def label(name, params):
    spec = TD_ONLY.get(name) or OPERATORS.get(name)
    p = dict((OPERATORS.get(name) or {}).get("params") or {}); p.update(params)
    return "TD " + spec["label"].format(**p) if name not in TD_ONLY else spec["label"].format(**p)


def tag_for(i, name, params):
    t = "%03d_%s" % (i, name) + ("" if not params else "_" + "_".join("%s%s" % (k, v) for k, v in params.items()))
    return t.replace(".", "p").replace(" ", "")


def specs(cfg, vdb_dir="results/houdini/vdb"):
    out_root = cfg.get("out", "results/td")
    rows = []
    for key in cfg["cubes"]:
        target = np.load(os.path.join(vdb_dir, key + "_target.npy")).astype(np.float64)
        plain_scale = float(np.percentile(target, 99.8)) + 1e-12      # td plain render = target exactly (gate)
        jobs = [dict(name="reference", kind="volume", params={}, knobs={})]
        for e in cfg["operators"]:
            for params, knobs in expand(e):
                jobs.append(dict(name=e["name"], kind=e["kind"], params=params, knobs=knobs, twin=e.get("twin", e["name"])))
        for i, j in enumerate(jobs):
            tag = tag_for(i, j["name"], j["params"])
            rows.append(dict(j, cube=key, index=i, tag=tag, scale=plain_scale, label=label(j["name"], j["params"]) if j["name"] != "reference" else "TD plain (= clipped moment 0)",
                             raw=os.path.join(out_root, key, "raw", tag + ".npy")))
    os.makedirs(out_root, exist_ok=True)
    import matplotlib
    np.savez(os.path.join(out_root, "cmaps.npz"), **{n: matplotlib.colormaps[n](np.linspace(0, 1, 256)).astype(np.float32)
                                                       for n in ["gray", "inferno", "viridis", "jet"]})
    path = os.path.join(out_root, "specs.json")
    json.dump(rows, open(path, "w"), indent=1)
    print("%d frames over %d cubes -> %s" % (len(rows), len(cfg["cubes"]), path))
    return path


def _python_twin(cube, name, params, ref):
    """track a's image for the same knob on the same input td gets (the clipped cube), volume ops only.
    measures the renderer, not the clip (the clip cost is its own row in track a)."""
    if name not in OPERATORS or OPERATORS[name]["kind"] != "volume":
        return None
    import copy
    cc = copy.copy(cube)
    cc.T = np.clip(cube.T, 0, None)
    return apply_operator(cc, name, params)["img"]


def score(cfg, only=None):
    out_root = cfg.get("out", "results/td")
    all_specs = json.load(open(os.path.join(out_root, "specs.json")))
    dec0 = dict(cfg.get("decoder") or {})
    mode = dec0.pop("mode", "blind")
    vis = cfg.get("vis_jnd", 2.3)
    cards = {}
    for key, path in cfg["cubes"].items():
        if only and key != only:
            continue
        t0 = time.time()
        yb = (cfg.get("beams") or {}).get(key)
        cube = load_cube(path, name=key, n_edge=cfg.get("noise_edge_channels", 3), beam_fwhm_px=float(yb) if yb else None)
        m0 = moment0(cube)
        ref = render(cube.T, cube.dv)
        ref01 = norm_disp(ref)
        mask = sky_mask(m0, cube.sigma_m0, cfg.get("mask_k", 3.0), cube.valid)
        beam = float(cube.beam_fwhm_px or (cfg.get("controls") or {}).get("beam_fwhm_px", 2.0))
        ctrl = controls(m0, ref, mask, beam_fwhm_px=beam, decoder=dec0, jnd_vis=vis)
        bands = bands_from_controls(ctrl); bands["source"] = "controls"
        out = os.path.join(out_root, key)
        os.makedirs(os.path.join(out, "frames"), exist_ok=True)
        json.dump(dict(controls=ctrl, bands=bands), open(os.path.join(out, "controls.json"), "w"), indent=1)
        chash = cube_hash(path)
        rows = []
        for sp in [s for s in all_specs if s["cube"] == key]:
            raw = np.load(sp["raw"]).astype(np.float64)
            name, params = sp["name"], sp["params"]
            base = OPERATORS.get(name) or TD_ONLY.get(name) or {}
            family = base.get("family", "post" if sp["kind"] == "post" else "volume")
            twin_diff = None
            if sp["kind"] == "volume":
                img = center_crop_like(raw, ref) if raw.shape != ref.shape else raw
                fr = dict(img=img, scale=disp_scale(img), img01=norm_disp(img), cmap="gray", ramp_transform=None)
                fr["rgb"] = colormap(fr["img01"], "gray")
                tw = _python_twin(cube, name, params, ref)
                if tw is not None and tw.shape == img.shape:
                    twin_diff = dict(max_abs_of_peak=float(np.abs(img - tw).max() / (np.abs(tw).max() + 1e-12)),
                                     rms_of_peak=float(np.sqrt(((img - tw) ** 2).mean()) / (np.abs(tw).max() + 1e-12)))
            else:
                cmap = params.get("cmap", "gray")
                fr = dict(rgb=np.clip(raw, 0, 1), cmap=cmap, scale=sp["scale"], ramp_transform=None)
            recovered, rec01 = decode_frame(fr, mode=mode, **dec0)
            s = score_frame(m0, ref01, recovered, mask, fr["rgb"], zero_color_lab(fr["cmap"]), vis)
            s["flip"] = flip_score(colormap(ref01, "gray"), fr["rgb"]) if fr["rgb"].shape[:2] == ref01.shape else None
            row = dict(index=sp["index"], name=name, params=params, knobs=sp["knobs"], label=sp["label"], family=family, kind=sp["kind"],
                       expected_class=base.get("cls"), twin=sp.get("twin", name), cmap=fr["cmap"], decoder=dict(mode=mode, **dec0), vis_jnd=vis,
                       scores=s, data_recovered=s["headline"]["data_recovered"], structure_kept=s["headline"]["structure_kept"],
                       flux_visible=s["headline"]["flux_visible"], band=classify(s["headline"]["data_recovered"], bands),
                       twin_image_diff=twin_diff, renderer="touchdesigner", cube=key, cube_hash=chash, version=__version__)
            if name == "orbit":
                cm = render(cube.T, cube.dv, theta_deg=params["theta"], aspect=params["aspect"])
                cm_c = center_crop_like(cm, ref) if cm.shape != ref.shape else cm
                s2 = score_frame(cm_c, norm_disp(cm_c), recovered, sky_mask(cm_c, cube.sigma_m0, 3.0, cube.valid if cm_c.shape == cube.valid.shape else None),
                                 fr["rgb"], zero_color_lab(fr["cmap"]), vis)
                row["camera_matched"] = s2["headline"]
            save_png(fr["rgb"], os.path.join(out, "frames", sp["tag"] + ".png"))
            json.dump(row, open(os.path.join(out, "frames", sp["tag"] + ".json"), "w"), indent=1)
            rows.append(row)
            print("  %-40s data %.3f  structure %.3f  flux %.2f  %-12s%s" % (row["label"], row["data_recovered"], row["structure_kept"], row["flux_visible"], row["band"],
                  "" if not twin_diff else "  vs python %.2f%%" % (100 * twin_diff["max_abs_of_peak"])))
        card = dict(cube=key, path=path, cube_hash=chash, shape=list(cube.shape), dv=cube.dv, sigma=cube.sigma, renderer="touchdesigner",
                    m0_max=float(m0.max()), mask_pixels=int(mask.sum()), decoder=dict(mode=mode, **dec0), vis_jnd=vis, beam_fwhm_px=beam,
                    cube_meta=cube.meta, bands=bands, controls=ctrl, rows=rows, version=__version__, seconds=round(time.time() - t0, 1))
        json.dump(card, open(os.path.join(out, "scorecard.json"), "w"), indent=1)
        print("[%s] %d frames scored in %.1f s -> %s" % (key, len(rows), card["seconds"], os.path.join(out, "scorecard.json")))
        cards[key] = card
    return cards


def _series(card, name):
    rows = [r for r in card["rows"] if r["name"] == name]
    return rows


def twins(cfg, a_root="results/v1", fig_dir="paper/figures"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy.stats import spearmanr
    out_root = cfg.get("out", "results/td")
    summary = {}
    for key in cfg["cubes"]:
        tp, ap_ = os.path.join(out_root, key, "scorecard.json"), os.path.join(a_root, key, "scorecard.json")
        if not (os.path.exists(tp) and os.path.exists(ap_)):
            print("skip %s (missing %s)" % (key, tp if not os.path.exists(tp) else ap_)); continue
        td, a = json.load(open(tp)), json.load(open(ap_))
        names = [e["name"] for e in cfg["operators"]]
        twin_of = {e["name"]: e.get("twin", e["name"]) for e in cfg["operators"]}
        ncol = 4; nrow = int(np.ceil(len(names) / ncol))
        fig, axs = plt.subplots(nrow, ncol, figsize=(3.2 * ncol, 2.4 * nrow), squeeze=False)
        pairs, rows_out = [], []
        b = td["bands"]
        for ax, name in zip(axs.flat, names):
            t_rows = _series(td, name)
            a_rows = _series(a, twin_of[name])
            def xy(rows):
                if not rows:
                    return [], [], []
                keys = [k for k in rows[0]["params"] if k != "aspect"]
                k = keys[0] if keys else None
                if name == "orbit":
                    rows = [r for r in rows if r["params"].get("aspect") == 1]
                xs = [r["params"][k] if k else 0 for r in rows]
                return xs, [r["data_recovered"] for r in rows], rows
            tx, ty, tr = xy(t_rows)
            ax_, ay, ar = xy(a_rows)
            cat = any(isinstance(x, str) for x in tx + ax_)
            if cat:
                allx = sorted(set(tx) | set(ax_)); pos = {x: i for i, x in enumerate(allx)}
                ax.plot([pos[x] for x in ax_], ay, "o", color="0.5", label="python (track a)")
                ax.plot([pos[x] for x in tx], ty, "s", color="C3", mfc="none", label="touchdesigner")
                ax.set_xticks(range(len(allx))); ax.set_xticklabels(allx, fontsize=7)
            else:
                if ax_:
                    ax.plot(ax_, ay, "o-", color="0.5", ms=3, label="python (track a)")
                ax.plot(tx, ty, "s-", color="C3", ms=3, mfc="none", label="touchdesigner")
            ax.axhspan(b["preserving_min"], 1.0, color="g", alpha=0.07); ax.axhspan(b["conditional_min"], b["preserving_min"], color="y", alpha=0.07)
            lo = min(ty + ay + [b["conditional_min"]]); ax.set_ylim(max(lo - 0.03 * (1.0 - lo) - 0.01, -0.2), 1.0 + 0.03 * (1.0 - lo) + 0.002)
            ax.set_title(name + ("" if twin_of[name] == name else " (vs %s)" % twin_of[name]) + ("" if ar else ", td only"), fontsize=8)
            ax.tick_params(labelsize=7)
            for r in tr:
                m = [q for q in ar if q["params"] == {k: v for k, v in r["params"].items()}] if twin_of[name] == name else []
                rows_out.append(dict(name=name, params=r["params"], td=r["data_recovered"], python=m[0]["data_recovered"] if m else None,
                                     td_band=r["band"], python_band=m[0]["band"] if m else None, twin_image_diff=r.get("twin_image_diff")))
                if m:
                    pairs.append((r["data_recovered"], m[0]["data_recovered"]))
        for ax in list(axs.flat)[len(names):]:
            ax.axis("off")
        axs.flat[0].legend(fontsize=6, loc="lower left")
        fig.suptitle("%s: data recovered per knob, touchdesigner (red) vs python proof renderer (gray). green = preserving band" % key, fontsize=9)
        fig.tight_layout(); os.makedirs(fig_dir, exist_ok=True)
        fp = os.path.join(fig_dir, "fig_twins_%s.png" % key); fig.savefig(fp, dpi=150); plt.close(fig)
        p = np.array(pairs)
        summary[key] = dict(n_pairs=len(pairs), spearman=float(spearmanr(p[:, 0], p[:, 1])[0]) if len(p) > 2 else None,
                            mean_abs_diff=float(np.abs(p[:, 0] - p[:, 1]).mean()) if len(p) else None,
                            band_agreement=float(np.mean([r["td_band"] == r["python_band"] for r in rows_out if r["python_band"]])) if pairs else None,
                            rows=rows_out, figure=fp)
        print("%-8s %d twin frames  spearman td vs python %.3f  mean |diff| %.3f  same band %.0f%%  -> %s" % (
            key, len(pairs), summary[key]["spearman"] or float("nan"), summary[key]["mean_abs_diff"] or float("nan"), 100 * (summary[key]["band_agreement"] or 0), fp))
    json.dump(summary, open(os.path.join(out_root, "twins.json"), "w"), indent=1)
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description="touchdesigner sweep: specs -> (td renders) -> score -> twins")
    ap.add_argument("step", choices=["specs", "score", "twins"])
    ap.add_argument("yaml", nargs="?", default="sweeps/td_v1.yaml")
    ap.add_argument("--cube", default=None)
    a = ap.parse_args(argv)
    cfg = load_cfg(a.yaml)
    if a.step == "specs":
        specs(cfg)
    elif a.step == "score":
        score(cfg, a.cube)
    else:
        twins(cfg)


if __name__ == "__main__":
    main()
