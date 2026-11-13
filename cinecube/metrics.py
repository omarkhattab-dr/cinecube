import numpy as np
from scipy import ndimage
from scipy.stats import spearmanr, pearsonr
from skimage import color as skcolor
from skimage.metrics import structural_similarity

from .render import norm_disp
from .operators import colormap
from .decode import decode_rgb, zero_color_lab, quantize8

FWHM2SIGMA = 1.0 / 2.3548


def data_recovered(m0, recovered, mask=None):
    r, q = m0.ravel(), np.asarray(recovered).ravel()
    out = {}
    for tag, sel in (("all", np.ones_like(r, dtype=bool)), ("mask", None if mask is None else mask.ravel())):
        if sel is None:
            continue
        rr, qq = r[sel], q[sel]
        if rr.size < 3 or np.std(qq) == 0:
            out[tag] = dict(spearman=0.0, pearson=0.0, rmse=float(np.sqrt(np.mean((rr - qq) ** 2))))
            continue
        out[tag] = dict(spearman=float(spearmanr(rr, qq).correlation),
                        pearson=float(pearsonr(rr, qq)[0]),
                        rmse=float(np.sqrt(np.mean((rr - qq) ** 2))))
    return out


def _ssim(a, b):
    return float(structural_similarity(a, b, data_range=1.0, gaussian_weights=True, sigma=1.5, use_sample_covariance=False))


def structure_kept(ref01, out01):
    s1 = _ssim(ref01, out01)
    a = ndimage.zoom(ref01, 0.5, order=1)
    b = ndimage.zoom(out01, 0.5, order=1)
    return dict(ssim=s1, ssim_2x=_ssim(a, b))


def visible_mask(rgb, zero_lab, jnd_vis=2.3):
    lab = skcolor.rgb2lab(quantize8(rgb))
    d = skcolor.deltaE_ciede2000(lab, np.broadcast_to(zero_lab, lab.shape))
    return d >= jnd_vis


def flux_visible(m0, mask, rgb=None, zero_lab=None, out01=None, jnd_vis=2.3):
    sig = mask
    tot = float(m0[sig].sum()) + 1e-12
    out = {}
    if rgb is not None and zero_lab is not None and rgb.shape[:2] == m0.shape:
        vis = visible_mask(rgb, zero_lab, jnd_vis) & sig
        out["flux"] = float(m0[vis].sum() / tot)
    if out01 is not None:
        out["flux_v0_2pct"] = float(m0[(out01 >= 0.02) & sig].sum() / tot)
        out["flux_legacy20"] = float(m0[(out01 > 0.2) & sig].sum() / tot)
    if "flux" not in out:
        out["flux"] = out.get("flux_v0_2pct", float("nan"))
        out["flux_note"] = "no rgb, used decoded value >= 2%"
    return out


def score_frame(m0, ref01, recovered, mask, rgb=None, zero_lab=None, jnd_vis=2.3):
    out01 = norm_disp(recovered)
    s = {}
    s["data"] = data_recovered(m0, recovered, mask)
    s["structure"] = structure_kept(ref01, out01)
    s["flux"] = flux_visible(m0, mask, rgb, zero_lab, out01, jnd_vis)
    s["headline"] = dict(data_recovered=s["data"]["mask"]["spearman"] if "mask" in s["data"] else s["data"]["all"]["spearman"],
                         structure_kept=s["structure"]["ssim"], flux_visible=s["flux"]["flux"])
    return s


def flip_score(rgb_ref, rgb_test):
    try:
        import flip_evaluator as flip
        _, mean_err, _ = flip.evaluate(rgb_ref.astype(np.float32), rgb_test.astype(np.float32), "LDR")
        return float(mean_err)
    except Exception:
        return None


def controls(m0, ref, mask, beam_fwhm_px=2.0, cmap="gray", decoder=None, jnd_vis=2.3):
    decoder = dict(decoder or {})
    decoder.pop("mode", None)
    ref01 = norm_disp(ref)
    scale = float(np.percentile(ref, 99.8)) + 1e-12
    zero = zero_color_lab(cmap)
    rows = {}

    def through(img, label):
        img01 = norm_disp(img)
        rgb = colormap(img01, cmap)
        rec01 = decode_rgb(rgb, cmap, **decoder)
        s = score_frame(m0, ref01, rec01 * float(np.percentile(img, 99.8) + 1e-12), mask, rgb, zero, jnd_vis)
        return dict(**s["headline"], note=label)

    rows["ceiling"] = through(ref, "the reference display decoded, deterministic")

    sigma = 2.0 * beam_fwhm_px * FWHM2SIGMA
    rows["beam_blur"] = through(ndimage.gaussian_filter(ref, sigma), "reference blurred to 2x the beam (fwhm %.1f px, sigma %.2f px)" % (beam_fwhm_px, sigma))

    rng = np.random.default_rng(0)
    rows["noise_only"] = through(np.abs(rng.normal(0, 1, ref.shape)) * scale * 0.3, "pure noise frame")

    shuffled = ref.ravel().copy(); rng.shuffle(shuffled)
    rows["shuffled"] = through(shuffled.reshape(ref.shape), "reference pixels permuted")

    warped = colormap(ref01 ** 0.5, "gray")
    rec01 = decode_rgb(warped, "gray", **decoder)
    s = score_frame(m0, ref01, rec01 * scale, mask, warped, zero, jnd_vis)
    rows["random_ramp"] = dict(**s["headline"], note="gray with gamma 0.5, decoded as linear gray")
    return rows


def bands_from_controls(ctrl):
    return dict(preserving_min=ctrl["ceiling"]["data_recovered"],
                conditional_min=ctrl["beam_blur"]["data_recovered"],
                structure_preserving_min=ctrl["ceiling"]["structure_kept"],
                structure_conditional_min=ctrl["beam_blur"]["structure_kept"])


def classify(value, bands, key="data"):
    lo = bands["conditional_min"] if key == "data" else bands["structure_conditional_min"]
    hi = bands["preserving_min"] if key == "data" else bands["structure_preserving_min"]
    if value >= hi - 1e-9:
        return "preserving"
    if value >= lo - 1e-9:
        return "conditional"
    return "distorting"
