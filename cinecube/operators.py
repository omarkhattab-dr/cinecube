import numpy as np
from scipy import ndimage
import matplotlib

matplotlib.use("Agg")

from .render import render, norm_disp, disp_scale, center_crop_like


def tf_linear(E, cube):
    return E


def tf_log(E, cube):
    return np.log10(1.0 + np.clip(E, 0, None) / cube.sigma)


def tf_asinh(E, cube):
    return np.arcsinh(np.clip(E, 0, None) / cube.sigma)


def tf_threshold(E, cube, k=3.0):
    return np.where(E > k * cube.sigma, E, 0.0)


def colormap(img01, name="gray"):
    return matplotlib.colormaps[name](img01)[..., :3]


def grade_teal_orange(rgb, strength=0.6):
    lum = rgb.mean(axis=-1, keepdims=True)
    s = 1.0 / (1.0 + np.exp(-8 * (lum - 0.5)))
    s = (s - s.min()) / (s.max() - s.min() + 1e-12)
    teal = np.array([0.0, 0.55, 0.6])
    orange = np.array([1.0, 0.6, 0.2])
    tint = (1 - s) * teal + s * orange
    return np.clip(rgb * (1 - strength) + strength * (s * tint), 0, 1)


def grade_nonmonotone(rgb, mix=0.7):
    lum = rgb.mean(axis=-1, keepdims=True)
    folded = 1 - np.abs(2 * lum - 1)
    return np.clip(rgb * (1 - mix) + mix * folded, 0, 1)


def bloom(rgb, threshold=0.35, sigma=7.0, gain=1.6):
    bright = np.clip(rgb - threshold, 0, None)
    glow = np.stack([ndimage.gaussian_filter(bright[..., c], sigma) for c in range(3)], axis=-1)
    return np.clip(rgb + gain * glow, 0, 1)


def vignette(rgb, strength=0.5):
    ny, nx = rgb.shape[:2]
    y, x = np.mgrid[0:ny, 0:nx]
    r = np.sqrt(((x - nx / 2) / (nx / 2)) ** 2 + ((y - ny / 2) / (ny / 2)) ** 2)
    mask = 1 - strength * np.clip(r, 0, 1) ** 2
    return np.clip(rgb * mask[..., None], 0, 1)


def grain(rgb, sigma=0.03, seed=1):
    rng = np.random.default_rng(seed)
    return np.clip(rgb + rng.normal(0, sigma, rgb.shape), 0, 1)


def spectral_bin(T, factor=2):
    nv = (T.shape[0] // factor) * factor
    return T[:nv].reshape(nv // factor, factor, *T.shape[1:]).mean(axis=1)


def sky_resample(img, factor=2, method="nearest"):
    small = ndimage.zoom(img, 1.0 / factor, order=1)
    order = 0 if method == "nearest" else 1
    back = ndimage.zoom(small, factor, order=order)
    out = np.zeros_like(img)
    h, w = min(back.shape[0], img.shape[0]), min(back.shape[1], img.shape[1])
    out[:h, :w] = back[:h, :w]
    return out


OPERATORS = {
    "reference": dict(family="reference", kind="volume", params={}, cls="none", label="Reference (= moment 0)"),
    "clip": dict(family="transfer", kind="volume", params={}, cls="deleter", label="Clip at 0 (no negative emission)"),
    "log": dict(family="transfer", kind="volume", params={}, cls="jumbler", label="Log stretch"),
    "asinh": dict(family="transfer", kind="volume", params={}, cls="jumbler", label="Asinh stretch"),
    "threshold": dict(family="transfer", kind="volume", params={"k": 3.0}, cls="confuser", label="Threshold at {k:g} sigma"),
    "absorb": dict(family="compositing", kind="volume", params={"tau": 0.35}, cls="confuser", label="Absorption, tau {tau:g}"),
    "mip": dict(family="compositing", kind="volume", params={}, cls="confuser", label="Max intensity projection"),
    "colormap": dict(family="color", kind="image", params={"cmap": "inferno"}, cls="jumbler", label="Colormap {cmap}"),
    "grade_teal_orange": dict(family="color", kind="image", params={"strength": 0.6}, cls="misleader", label="Teal-orange grade {strength:g}"),
    "grade_nonmonotone": dict(family="color", kind="image", params={"mix": 0.7}, cls="jumbler", label="Non-monotone grade"),
    "orbit": dict(family="camera", kind="volume", params={"theta": 30.0, "aspect": 1.0}, cls="misleader", label="Orbit {theta:g} deg, stretch {aspect:g}x"),
    "dof": dict(family="dof", kind="volume", params={"sigma": 3.0}, cls="hallucinator", label="Depth of field {sigma:g}"),
    "shading": dict(family="lighting", kind="volume", params={"strength": 0.7}, cls="hallucinator", label="Lighting {strength:g}"),
    "bloom": dict(family="post", kind="image", params={"gain": 1.6, "sigma": 7.0, "threshold": 0.35}, cls="hallucinator", label="Bloom {gain:g}"),
    "vignette": dict(family="post", kind="image", params={"strength": 0.5}, cls="hallucinator", label="Vignette {strength:g}"),
    "grain": dict(family="post", kind="image", params={"sigma": 0.03}, cls="hallucinator", label="Grain {sigma:g}"),
    "spectral_bin": dict(family="resampling", kind="volume", params={"factor": 2}, cls="confuser", label="Spectral binning {factor}x"),
    "sky_resample": dict(family="resampling", kind="volume", params={"factor": 2, "method": "nearest"}, cls="confuser", label="Sky resample {factor}x {method}"),
}

FAMILIES = ["transfer", "compositing", "color", "camera", "dof", "lighting", "post", "resampling"]


def label_for(name, params):
    return OPERATORS[name]["label"].format(**params)


def _render_kwargs(name, p, cube):
    if name == "reference":
        return {}
    if name == "log":
        return {"tf": lambda e: tf_log(e, cube)}
    if name == "asinh":
        return {"tf": lambda e: tf_asinh(e, cube)}
    if name == "threshold":
        return {"tf": lambda e: tf_threshold(e, cube, p["k"])}
    if name == "absorb":
        return {"composite": "absorb", "kappa": p["tau"] / (np.max(cube.T) * cube.dv)}
    if name == "mip":
        return {"composite": "mip"}
    if name == "orbit":
        return {"theta_deg": p["theta"], "aspect": p["aspect"]}
    if name == "dof":
        return {"dof_sigma": p["sigma"]}
    if name == "shading":
        return {"shading": p["strength"]}
    if name in ("spectral_bin", "sky_resample"):
        return {}
    raise KeyError(name)


def apply_operator(cube, name, params=None, cmap="gray"):
    spec = OPERATORS[name]
    p = dict(spec["params"])
    p.update(params or {})
    ref = render(cube.T, cube.dv)
    out = dict(name=name, params=p, kind=spec["kind"], family=spec["family"], cls=spec["cls"], label=label_for(name, p),
               cmap=cmap, ramp_transform=None)

    if spec["kind"] == "volume":
        if name == "clip":
            img_full = render(np.clip(cube.T, 0, None), cube.dv)
        elif name == "spectral_bin":
            Tb = spectral_bin(cube.T, int(p["factor"]))
            img_full = render(Tb, cube.dv * int(p["factor"]))
        elif name == "sky_resample":
            img_full = sky_resample(ref, int(p["factor"]), p["method"])
        else:
            img_full = render(cube.T, cube.dv, **_render_kwargs(name, p, cube))
        img = center_crop_like(img_full, ref) if img_full.shape != ref.shape else img_full
        out.update(img=img, img_full=img_full, scale=disp_scale(img), img01=norm_disp(img))
        out["rgb"] = colormap(out["img01"], cmap)
        return out

    if name == "colormap":
        cmap = p["cmap"]
        out["cmap"] = cmap
    ref01 = norm_disp(ref)
    rgb = colormap(ref01, cmap)
    if name == "grade_teal_orange":
        fn = lambda a: grade_teal_orange(a, p["strength"])
        rgb = fn(rgb); out["ramp_transform"] = fn
    elif name == "grade_nonmonotone":
        fn = lambda a: grade_nonmonotone(a, p["mix"])
        rgb = fn(rgb); out["ramp_transform"] = fn
    elif name == "bloom":
        rgb = bloom(rgb, p["threshold"], p["sigma"], p["gain"])
    elif name == "vignette":
        rgb = vignette(rgb, p["strength"])
    elif name == "grain":
        rgb = grain(rgb, p["sigma"])
    out.update(img=ref, img_full=ref, scale=disp_scale(ref), img01=ref01, rgb=rgb)
    return out
