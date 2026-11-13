import numpy as np
from scipy import ndimage


def render(T, dv, theta_deg=0.0, aspect=1.0, composite="additive", kappa=0.0,
           tf=None, dof_sigma=0.0, v_focus_index=None, shading=0.0):
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
        g = np.array(np.gradient(ndimage.gaussian_filter(E, 1.0)))
        gn = g / (np.linalg.norm(g, axis=0, keepdims=True) + 1e-9)
        light = np.array([0.0, -0.6, -0.8])
        lam = np.clip((gn * light[:, None, None, None]).sum(axis=0), 0, 1)
        E = E * (1.0 - shading + shading * lam)

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
        img = np.zeros(E.shape[1:])
        trans = np.ones(E.shape[1:])
        for slab in E:
            a = 1.0 - np.exp(-kappa * np.clip(slab, 0, None) * ds)
            img += trans * slab * ds
            trans *= (1.0 - a)
        return img
    raise ValueError("composite must be additive, absorb or mip, got %r" % composite)


def reference(cube):
    return render(cube.T, cube.dv)


def camera_matched_reference(cube, theta_deg, aspect=1.0):
    return render(cube.T, cube.dv, theta_deg=theta_deg, aspect=aspect)


def normalize(img, lo=None, hi=None):
    lo = np.nanmin(img) if lo is None else lo
    hi = np.nanmax(img) if hi is None else hi
    return np.clip((img - lo) / (hi - lo + 1e-12), 0, 1)


def norm_disp(img, p=99.8):
    scale = float(np.percentile(img, p)) + 1e-12
    return np.clip(img / scale, 0, 1)


def disp_scale(img, p=99.8):
    return float(np.percentile(img, p)) + 1e-12


def center_crop_like(img, ref):
    ny, nx = ref.shape
    y0 = max((img.shape[0] - ny) // 2, 0)
    x0 = max((img.shape[1] - nx) // 2, 0)
    out = img[y0:y0 + ny, x0:x0 + nx]
    pad = np.zeros_like(ref)
    pad[:out.shape[0], :out.shape[1]] = out
    return pad


def pad_to_square(img01):
    side = max(img01.shape)
    canvas = np.zeros((side, side))
    y0 = (side - img01.shape[0]) // 2
    x0 = (side - img01.shape[1]) // 2
    canvas[y0:y0 + img01.shape[0], x0:x0 + img01.shape[1]] = img01
    return canvas
