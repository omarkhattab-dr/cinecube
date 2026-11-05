"""
render.py - the ray marcher

one function render() does every camera / compositing variant. with defaults
(theta 0, aspect 1, additive, linear tf, no blur, no shading) it returns sum_v T*dv
= the moment0 map. tests/test_equivalence.py checks that every time.
"""
import numpy as np
from scipy import ndimage


def render(T, dv, theta_deg=0.0, aspect=1.0, composite="additive", kappa=0.0,
           tf=None, dof_sigma=0.0, v_focus_index=None, shading=0.0):
    """
    ray march T[v, y, x] -> 2d image

    theta_deg  camera orbit around the image vertical. 0 = looking down the v axis
    aspect     stretch of the v axis vs sky pixels (spectral aspect ratio)
    composite  "additive" (emission only), "absorb" (emission + absorption, opacity kappa), "mip"
    kappa      absorption per unit of T*dv, only for composite="absorb"
    tf         transfer function on T before integrating (None = linear)
    dof_sigma  depth of field, gaussian blur per channel that grows with |channel - focus|
    shading    0 = none, else strength of a lambert term on the density gradient

    rotated renders come back bigger than the sky field, see center_crop_like() and
    camera_matched_reference() for the 2 ways to compare
    """
    E = T.astype(np.float64, copy=True)
    if tf is not None:
        E = tf(E)
    nv = E.shape[0]

    if dof_sigma > 0:
        f = nv // 2 if v_focus_index is None else v_focus_index
        for i in range(nv):
            s = dof_sigma * abs(i - f) / max(nv // 2, 1)
            if s > 0.05:
                E[i] = ndimage.gaussian_filter(E[i], s)

    if shading > 0:
        # fake light from upper left, voxels whose gradient faces it get brighter
        g = np.array(np.gradient(ndimage.gaussian_filter(E, 1.0)))
        gn = g / (np.linalg.norm(g, axis=0, keepdims=True) + 1e-9)
        light = np.array([0.0, -0.6, -0.8])  # (v, y, x)
        lam = np.clip((gn * light[:, None, None, None]).sum(axis=0), 0, 1)
        E = E * (1.0 - shading + shading * lam)

    # stretch v axis first, then orbit the camera around vertical
    if aspect != 1.0:
        E = ndimage.zoom(E, (aspect, 1, 1), order=1)
    if theta_deg != 0.0:
        E = ndimage.rotate(E, theta_deg, axes=(0, 2), reshape=True, order=1, mode="constant", cval=0.0)
    ds = dv / (aspect if aspect != 1.0 else 1.0)

    if composite == "additive":
        return (E * ds).sum(axis=0)
    if composite == "mip":
        return E.max(axis=0)
    if composite == "absorb":
        # front to back. each slab emits E*ds and blocks 1 - exp(-kappa*E*ds) of whats behind it
        img = np.zeros(E.shape[1:])
        trans = np.ones(E.shape[1:])
        for slab in E:
            a = 1.0 - np.exp(-kappa * np.clip(slab, 0, None) * ds)
            img += trans * slab * ds
            trans *= (1.0 - a)
        return img
    raise ValueError("composite must be additive, absorb or mip, got %r" % composite)


def reference(cube):
    """the reference render. additive, linear, ortho, down the v axis = moment 0"""
    return render(cube.T, cube.dv)


def camera_matched_reference(cube, theta_deg, aspect=1.0):
    """reference for a given camera. same orbit + stretch, linear, no absorption

    scoring an orbit frame against this instead of moment0 separates the operator from the
    viewpoint. the difference between the 2 scorings = the cost of the viewpoint itself,
    which is what the velocity-as-depth index is about
    """
    return render(cube.T, cube.dv, theta_deg=theta_deg, aspect=aspect)


def normalize(img, lo=None, hi=None):
    lo = np.nanmin(img) if lo is None else lo
    hi = np.nanmax(img) if hi is None else hi
    return np.clip((img - lo) / (hi - lo + 1e-12), 0, 1)


def norm_disp(img, p=99.8):
    """display normalization for every frame, black at 0 white at the p-th percentile

    returns the 0..1 image. the scale (that percentile) is what decode.to_physical() needs
    to go back to K km/s
    """
    scale = float(np.percentile(img, p)) + 1e-12
    return np.clip(img / scale, 0, 1)


def disp_scale(img, p=99.8):
    return float(np.percentile(img, p)) + 1e-12


def center_crop_like(img, ref):
    """rotated renders are bigger, crop the middle so the field matches the reference

    this is the old oct 27 way. part of what it measures is the crop itself, thats why
    camera_matched_reference() exists
    """
    ny, nx = ref.shape
    y0 = max((img.shape[0] - ny) // 2, 0)
    x0 = max((img.shape[1] - nx) // 2, 0)
    out = img[y0:y0 + ny, x0:x0 + nx]
    pad = np.zeros_like(ref)
    pad[:out.shape[0], :out.shape[1]] = out
    return pad


def pad_to_square(img01):
    """non square render -> square black canvas, for galleries"""
    side = max(img01.shape)
    canvas = np.zeros((side, side))
    y0 = (side - img01.shape[0]) // 2
    x0 = (side - img01.shape[1]) // 2
    canvas[y0:y0 + img01.shape[0], x0:x0 + img01.shape[1]] = img01
    return canvas
