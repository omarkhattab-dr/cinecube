from functools import lru_cache

import numpy as np
from scipy.spatial import cKDTree
from skimage import color as skcolor
import matplotlib

matplotlib.use("Agg")

DEFAULTS = dict(recipe="jnd", jnd=2.9, n_ramp=1024, quantize=True, noise_sigma=1.5 / 255, seed=0)


@lru_cache(maxsize=32)
def _ramp_rgb(cmap, n_ramp):
    ramp01 = np.linspace(0, 1, n_ramp)
    return ramp01, matplotlib.colormaps[cmap](ramp01)[:, :3]


def ramp_lab(cmap, n_ramp=1024, ramp_transform=None):
    ramp01, rgb = _ramp_rgb(cmap, n_ramp)
    if ramp_transform is not None:
        rgb = np.asarray(ramp_transform(rgb.reshape(1, -1, 3))).reshape(-1, 3)
    lab = skcolor.rgb2lab(np.clip(rgb, 0, 1).reshape(1, -1, 3)).reshape(-1, 3)
    return ramp01, lab


def zero_color_lab(cmap, ramp_transform=None):
    _, lab = ramp_lab(cmap, 256, ramp_transform)
    return lab[0]


@lru_cache(maxsize=32)
def _bins_cached(cmap, jnd, n_ramp):
    return _bins(cmap, jnd, n_ramp, None)


def _bins(cmap, jnd, n_ramp, ramp_transform):
    ramp01, lab = ramp_lab(cmap, n_ramp, ramp_transform)
    step = skcolor.deltaE_ciede2000(lab[:-1], lab[1:])
    s = np.concatenate([[0.0], np.cumsum(step)])
    nb = max(1, int(np.ceil(s[-1] / jnd)))
    edges = np.linspace(0, s[-1], nb + 1)
    centers_s = 0.5 * (edges[:-1] + edges[1:])
    idx = np.searchsorted(s, centers_s).clip(0, len(s) - 1)
    return ramp01[idx], lab[idx], float(s[-1])


def ramp_bins(cmap, jnd=2.9, n_ramp=1024, ramp_transform=None):
    if ramp_transform is None:
        return _bins_cached(cmap, float(jnd), int(n_ramp))
    return _bins(cmap, jnd, n_ramp, ramp_transform)


def quantize8(rgb):
    return np.round(np.clip(np.asarray(rgb, dtype=np.float64), 0, 1) * 255) / 255


def nearest_de2000(lab_pixels, centers_lab, chunk=8192):
    out = np.empty(lab_pixels.shape[0], dtype=np.intp)
    for i in range(0, lab_pixels.shape[0], chunk):
        blk = lab_pixels[i:i + chunk]
        d = skcolor.deltaE_ciede2000(blk[:, None, :], centers_lab[None, :, :])
        out[i:i + chunk] = d.argmin(axis=1)
    return out


def invert_colormap(rgb, cmap="gray", ramp_transform=None, jnd=2.9, n_ramp=1024, quantize=True):
    centers01, centers_lab, _ = ramp_bins(cmap, jnd, n_ramp, ramp_transform)
    img = quantize8(rgb) if quantize else np.asarray(rgb, dtype=np.float64)
    lab = skcolor.rgb2lab(img).reshape(-1, 3)
    idx = nearest_de2000(lab, centers_lab)
    return centers01[idx].reshape(rgb.shape[:2])


def display_degrade(rgb, quantize=True, noise_sigma=1.5 / 255, seed=0):
    out = np.asarray(rgb, dtype=np.float64)
    if quantize:
        out = np.round(out * 255) / 255
    if noise_sigma > 0:
        rng = np.random.default_rng(seed)
        out = out + rng.normal(0, noise_sigma, out.shape)
    return np.clip(out, 0, 1)


def invert_colormap_legacy(rgb, cmap="gray", ramp_transform=None, quantize=True, noise_sigma=1.5 / 255, seed=0, n_ramp=256):
    ramp01, lab = ramp_lab(cmap, n_ramp, ramp_transform)
    tree = cKDTree(lab)
    degraded = display_degrade(rgb, quantize, noise_sigma, seed)
    flat = skcolor.rgb2lab(degraded).reshape(-1, 3)
    _, idx = tree.query(flat, k=1)
    return ramp01[idx].reshape(rgb.shape[:2])


def to_physical(rec01, scale):
    return rec01 * scale


def decode_rgb(rgb, cmap, ramp_transform=None, **kw):
    cfg = dict(DEFAULTS)
    cfg.update(kw)
    if cfg["recipe"] == "legacy":
        return invert_colormap_legacy(rgb, cmap, ramp_transform=ramp_transform, quantize=cfg["quantize"],
                                      noise_sigma=cfg["noise_sigma"], seed=cfg["seed"], n_ramp=256)
    return invert_colormap(rgb, cmap, ramp_transform=ramp_transform, jnd=cfg["jnd"], n_ramp=cfg["n_ramp"], quantize=cfg["quantize"])


def decode_frame(frame, mode="blind", **kw):
    transform = frame.get("ramp_transform") if mode == "informed" else None
    rec01 = decode_rgb(frame["rgb"], frame["cmap"], ramp_transform=transform, **kw)
    return to_physical(rec01, frame["scale"]), rec01
