"""
decode.py - get data values back out of a frame

recipe from bujack et al 2026: quantize to 8 bit, add a bit of display noise, go to CIELAB,
for every pixel take the nearest colormap entry. its position on the ramp (0..1) is the
recovered display value, the scale from render.norm_disp() brings it back to K km/s.

2 decoders:
    blind     only knows the base colormap (a viewer with the legend)
    informed  also knows a pointwise color transform (a grade) and undoes it by pushing
              the ramp through the same transform before the lookup
"""
from functools import lru_cache

import numpy as np
from scipy.spatial import cKDTree
from skimage import color as skcolor
import matplotlib

matplotlib.use("Agg")

DEFAULTS = dict(quantize=True, noise_sigma=1.5 / 255, seed=0, n_ramp=256)


@lru_cache(maxsize=32)
def _ramp_rgb(cmap, n_ramp):
    ramp01 = np.linspace(0, 1, n_ramp)
    return ramp01, matplotlib.colormaps[cmap](ramp01)[:, :3]


def ramp_lab(cmap, n_ramp=256, ramp_transform=None):
    """the colormap ramp in CIELAB, optionally pushed through a pointwise transform"""
    ramp01, rgb = _ramp_rgb(cmap, n_ramp)
    if ramp_transform is not None:
        rgb = np.asarray(ramp_transform(rgb.reshape(1, -1, 3))).reshape(-1, 3)
    lab = skcolor.rgb2lab(rgb.reshape(1, -1, 3)).reshape(-1, 3)
    return ramp01, lab


def display_degrade(rgb, quantize=True, noise_sigma=1.5 / 255, seed=0):
    """what a viewer actually gets, 8 bit + a little display noise. fixed seed"""
    out = np.asarray(rgb, dtype=np.float64)
    if quantize:
        out = np.round(out * 255) / 255
    if noise_sigma > 0:
        rng = np.random.default_rng(seed)
        out = out + rng.normal(0, noise_sigma, out.shape)
    return np.clip(out, 0, 1)


def invert_colormap(rgb, cmap="gray", ramp_transform=None, quantize=True, noise_sigma=1.5 / 255, seed=0, n_ramp=256):
    """recover the 0..1 display value per pixel, nearest ramp color in CIELAB

    ramp_transform=None -> blind. pass the frames grade -> informed
    """
    ramp01, lab = ramp_lab(cmap, n_ramp, ramp_transform)
    tree = cKDTree(lab)
    degraded = display_degrade(rgb, quantize, noise_sigma, seed)
    flat = skcolor.rgb2lab(degraded).reshape(-1, 3)
    _, idx = tree.query(flat, k=1)
    return ramp01[idx].reshape(rgb.shape[:2])


def to_physical(rec01, scale):
    """display value back to physical units with the scale norm_disp() used (99.8 pct)"""
    return rec01 * scale


def decode_frame(frame, mode="blind", **kw):
    """decode an apply_operator() result -> (recovered physical, recovered01)"""
    cfg = dict(DEFAULTS)
    cfg.update(kw)
    cfg.pop("n_ramp", None)
    transform = frame.get("ramp_transform") if mode == "informed" else None
    rec01 = invert_colormap(frame["rgb"], frame["cmap"], ramp_transform=transform,
                            quantize=cfg["quantize"], noise_sigma=cfg["noise_sigma"], seed=cfg["seed"])
    return to_physical(rec01, frame["scale"]), rec01
