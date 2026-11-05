"""
figures.py - every paper figure, from the json in results/, nothing by hand

    python -m cinecube.figures results/v1 paper/figures

for each cube folder with a scorecard.json:
    fig_ladder_<cube>.png     operators ranked by data recovered, with structure + flux
    fig_families_<cube>.png   score vs parameter for every family that got swept, bands shaded
    fig_gallery_<cube>.png    frames in a grid with their 3 numbers
plus fig_index.png if results/<v>/index*.json is there, fig_envelope.png if envelope.json is there
(make envelope), and fig_equivalence.png from l1448.
print style: white bg, 300 dpi
"""
import argparse
import glob
import json
import os

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from PIL import Image

GOOD, WARN, BAD, INK, MUTED = "#2a9d8f", "#e9a23b", "#d1495b", "#1b1f2a", "#6b7280"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False, "axes.spines.right": False})


def band_color(b):
    return {"preserving": GOOD, "conditional": WARN, "distorting": BAD}.get(b, MUTED)


def _defaults_rows(card):
    """1 row per operator, the one at the registry defaults if it was swept, else the middle of its grid"""
    from .operators import OPERATORS
    groups = {}
    for r in card["rows"]:
        if r["name"] != "reference":
            groups.setdefault(r["name"], []).append(r)
    rows = []
    for name, grp in groups.items():
        defaults = OPERATORS.get(name, {}).get("params", {})
        hit = [r for r in grp if all(r["params"].get(k) == v for k, v in defaults.items())]
        rows.append(hit[0] if hit else grp[len(grp) // 2])
    return rows


def ladder(card, out):
    rows = sorted(_defaults_rows(card), key=lambda r: -r["data_recovered"])
    n = len(rows)
    fig, ax = plt.subplots(figsize=(7.2, 0.28 * n + 1.0))
    ax.set_xlim(0, 10.2); ax.set_ylim(-1.3, n); ax.axis("off")
    cols = [("data recovered", 3.2), ("structure kept", 5.7), ("flux visible", 8.2)]
    for lab, x in cols:
        ax.text(x + 0.9, n - 0.2, lab, ha="center", va="bottom", color=MUTED, fontsize=8)
    for k, r in enumerate(rows):
        y = n - 1 - k
        c = band_color(r["band"])
        ax.text(3.05, y, r["label"], ha="right", va="center", fontsize=8, color=INK)
        for (lab, x), val in zip(cols, [r["data_recovered"], r["structure_kept"], r["flux_visible"]]):
            ax.add_patch(Rectangle((x, y - 0.3), 1.8, 0.6, color="#e5e7eb"))
            ax.add_patch(Rectangle((x, y - 0.3), 1.8 * max(min(val, 1), 0), 0.6, color=c))
            ax.text(x + 1.85, y, "%.3f" % val if lab == "data recovered" else "%.2f" % val, va="center", fontsize=7.5, color=INK)
    b = card["bands"]
    ax.text(0.1, -1.0, "bands from controls: preserving >= %.3f (ceiling), conditional >= %.3f (2x beam), on data recovered" % (b["preserving_min"], b["conditional_min"]), fontsize=7, color=MUTED)
    fig.savefig(out, dpi=300, bbox_inches="tight"); plt.close(fig)


def families(card, out):
    """every operator swept over a numeric param -> score vs that param"""
    groups = {}
    for r in card["rows"]:
        if r["name"] == "reference":
            continue
        numeric = [k for k, v in r["params"].items() if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if not numeric:
            continue
        key = r["name"]
        groups.setdefault(key, []).append(r)
    groups = {k: v for k, v in groups.items() if len(v) >= 3}
    if not groups:
        return False
    n = len(groups)
    ncol = min(4, n); nrow = int(np.ceil(n / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(3.0 * ncol, 2.4 * nrow), squeeze=False)
    b = card["bands"]
    for ax, (name, rows) in zip(axes.ravel(), groups.items()):
        # the param that varies the most is the x axis
        keys = [k for k in rows[0]["params"] if isinstance(rows[0]["params"][k], (int, float)) and not isinstance(rows[0]["params"][k], bool)]
        var = max(keys, key=lambda k: len(set(r["params"][k] for r in rows)))
        others = sorted(set(tuple((k, r["params"][k]) for k in rows[0]["params"] if k != var) for r in rows))
        for o in others:
            sub = sorted([r for r in rows if tuple((k, r["params"][k]) for k in rows[0]["params"] if k != var) == o], key=lambda r: r["params"][var])
            xs = [r["params"][var] for r in sub]
            tag = ", ".join("%s %s" % kv for kv in o) if o else ""
            ax.plot(xs, [r["data_recovered"] for r in sub], "-o", ms=3, color=INK, label=("data " + tag).strip())
            ax.plot(xs, [r["structure_kept"] for r in sub], "--s", ms=3, color=MUTED, label=("structure " + tag).strip())
            ax.plot(xs, [r["flux_visible"] for r in sub], ":^", ms=3, color="#4b6cb7", label=("flux " + tag).strip())
        ax.axhspan(b["preserving_min"], 1.02, color=GOOD, alpha=0.08)
        ax.axhspan(b["conditional_min"], b["preserving_min"], color=WARN, alpha=0.08)
        ax.axhspan(0, b["conditional_min"], color=BAD, alpha=0.06)
        ax.set_ylim(0, 1.02); ax.set_title(name, fontsize=9); ax.set_xlabel(var, fontsize=8)
        ax.tick_params(labelsize=7)
        if len(others) <= 3:
            ax.legend(fontsize=5.5, frameon=False)
    for ax in axes.ravel()[n:]:
        ax.axis("off")
    fig.tight_layout(); fig.savefig(out, dpi=300); plt.close(fig)
    return True


def gallery(card, frames_dir, out, max_n=20):
    rows = card["rows"][:max_n]
    ncol = 5; nrow = int(np.ceil(len(rows) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(2.0 * ncol, 2.35 * nrow), squeeze=False)
    for ax in axes.ravel():
        ax.axis("off")
    pngs = sorted(glob.glob(os.path.join(frames_dir, "*.png")))
    for ax, r in zip(axes.ravel(), rows):
        png = [p for p in pngs if os.path.basename(p).startswith("%03d_" % r["index"])]
        if png:
            ax.imshow(np.asarray(Image.open(png[0])))
        ax.set_title(r["label"], fontsize=7, pad=2)
        ax.text(0.5, -0.04, "%.2f | %.2f | %d%%" % (r["data_recovered"], r["structure_kept"], round(100 * r["flux_visible"])),
                transform=ax.transAxes, ha="center", va="top", fontsize=7, color=band_color(r["band"]), fontweight="bold")
    fig.suptitle("under each: data recovered | structure kept | flux visible", fontsize=8, color=MUTED, y=0.995)
    fig.tight_layout(); fig.savefig(out, dpi=300); plt.close(fig)


def index_figure(paths, out):
    fig, axes = plt.subplots(1, len(paths), figsize=(3.3 * len(paths), 2.8), squeeze=False)
    for ax, p in zip(axes.ravel(), paths):
        d = json.load(open(p))
        for s in sorted(set(r["stretch"] for r in d["rows"])):
            sub = sorted([r for r in d["rows"] if r["stretch"] == s], key=lambda r: r["theta"])
            ax.plot([r["theta"] for r in sub], [r["one_minus_ssim"] for r in sub], "-o", ms=3, label="stretch %gx" % s)
        ax.set_xlabel("orbit angle (deg)"); ax.set_ylabel("index (1 - SSIM)"); ax.set_ylim(0, 1)
        ax.set_title("inclination %s deg" % d.get("inc_deg"), fontsize=9); ax.legend(fontsize=7, frameon=False)
    fig.tight_layout(); fig.savefig(out, dpi=300); plt.close(fig)


def equivalence(cube_path, out):
    from .io import load_cube, moment0
    from .render import render
    cube = load_cube(cube_path)
    m0 = moment0(cube); ref = render(cube.T, cube.dv)
    ny, nx = m0.shape; py, px = int(ny * 0.62), int(nx * 0.40)
    spec = cube.T[:, py, px]
    fig, axes = plt.subplots(1, 3, figsize=(8.5, 2.6), gridspec_kw=dict(width_ratios=[1.5, 1, 1]))
    axes[0].fill_between(cube.v, 0, spec, step="mid", alpha=0.3, color="#e9a23b"); axes[0].step(cube.v, spec, where="mid", color="#e9a23b")
    axes[0].set_xlabel("velocity (km/s)"); axes[0].set_ylabel("T (K)"); axes[0].set_title("spectrum at one pixel: area %.1f K km/s" % (spec.sum() * cube.dv), fontsize=8)
    for ax, img, t in ((axes[1], m0, "moment-0 map (spectral-cube)"), (axes[2], ref, "plain render (cinecube)")):
        ax.imshow(img, origin="lower", cmap="gray"); ax.plot(px, py, "o", mfc="none", mec="#e9a23b", ms=9); ax.set_title(t, fontsize=8); ax.axis("off")
    fig.suptitle("max |render - moment 0| = %.1e on a map whose peak is %.1f K km/s" % (np.abs(ref - m0).max(), m0.max()), fontsize=8, y=1.02)
    fig.tight_layout(); fig.savefig(out, dpi=300, bbox_inches="tight"); plt.close(fig)


def envelope_figure(path, out):
    """operators on y, 1 marker per object at its envelope position along its own grid (0 = smallest
    grid value, 1 = biggest). filled = stay conditional, hollow = stay preserving. x at the left edge =
    none (always out), triangle at the right edge = top of grid"""
    results = json.load(open(path))
    objs = [r["cube"] for r in results]
    marks = ["o", "s", "D", "^", "v", "P"]
    # one row per (operator, fixed) that has a numeric knob, same order for every object
    keys = []
    for r in results:
        for e in r["entries"]:
            if e.get("param") and not e.get("categorical"):
                k = (e["operator"], tuple(sorted((e.get("fixed") or {}).items())))
                if k not in keys:
                    keys.append(k)
    n = len(keys)
    fig, ax = plt.subplots(figsize=(7.2, 0.3 * n + 1.4))
    for i, (op, fixed) in enumerate(keys):
        y = n - 1 - i
        ax.axhline(y, color="#e5e7eb", lw=0.8, zorder=0)
        for j, r in enumerate(results):
            e = next((e for e in r["entries"] if e["operator"] == op and tuple(sorted((e.get("fixed") or {}).items())) == fixed), None)
            if e is None:
                continue
            grid = e["grid"]
            for band_key, filled in (("conditional", True), ("preserving", False)):
                b = e[band_key]
                if b["status"] == "none":
                    x, m = -0.04, "x"
                elif b["status"] == "top":
                    x, m = 1.04, ">"
                else:
                    x, m = grid.index(b["value"]) / max(len(grid) - 1, 1), marks[j % len(marks)]
                off = (j - (len(results) - 1) / 2) * 0.16
                ax.plot(x, y + off, marker=m, ms=5 if m in "x>" else 5.5, ls="none", color=plt.cm.tab10(j),
                        mfc=plt.cm.tab10(j) if filled else "white", mew=1.2, zorder=3)
        lab = op + (" (" + ", ".join("%s %s" % kv for kv in fixed) + ")" if fixed else "") + "  [%s]" % e["param"]
        ax.text(-0.08, y, lab, ha="right", va="center", fontsize=7.5, color=INK)
    for j, o in enumerate(objs):
        ax.plot([], [], marker=marks[j % len(marks)], ls="none", color=plt.cm.tab10(j), label=o)
    ax.plot([], [], marker="o", ls="none", color=MUTED, mfc="white", label="hollow = stay preserving")
    ax.plot([], [], marker="x", ls="none", color=MUTED, label="x = none, > = top of grid")
    ax.legend(fontsize=6.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=3)
    ax.set_xlim(-0.1, 1.1); ax.set_ylim(-0.8, n - 0.2); ax.set_yticks([])
    ax.set_xticks([0, 0.5, 1]); ax.set_xticklabels(["smallest grid value", "", "biggest"], fontsize=7)
    ax.spines["left"].set_visible(False)
    ax.set_title("envelope: how far each knob goes before it leaves the band", fontsize=9)
    fig.savefig(out, dpi=300, bbox_inches="tight"); plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description="build the figures from results")
    ap.add_argument("results", nargs="?", default="results/v1")
    ap.add_argument("out", nargs="?", default="paper/figures")
    ap.add_argument("--cube", default="data/l1448_13co.fits", help="cube for the equivalence figure")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    made = []
    for card_path in sorted(glob.glob(os.path.join(a.results, "*", "scorecard.json"))):
        card = json.load(open(card_path)); key = card["cube"]
        ladder(card, os.path.join(a.out, "fig_ladder_%s.png" % key)); made.append("fig_ladder_%s.png" % key)
        if families(card, os.path.join(a.out, "fig_families_%s.png" % key)):
            made.append("fig_families_%s.png" % key)
        gallery(card, os.path.join(os.path.dirname(card_path), "frames"), os.path.join(a.out, "fig_gallery_%s.png" % key)); made.append("fig_gallery_%s.png" % key)
    env = os.path.join(a.results, "envelope.json")
    if os.path.exists(env):
        envelope_figure(env, os.path.join(a.out, "fig_envelope.png")); made.append("fig_envelope.png")
    idx = sorted(glob.glob(os.path.join(a.results, "index*.json")))
    if idx:
        index_figure(idx, os.path.join(a.out, "fig_index.png")); made.append("fig_index.png")
    if os.path.exists(a.cube):
        equivalence(a.cube, os.path.join(a.out, "fig_equivalence.png")); made.append("fig_equivalence.png")
    print("made:", ", ".join(made))


if __name__ == "__main__":
    main()
