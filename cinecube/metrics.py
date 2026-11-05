"""
metrics.py - the 3 scores, the controls, the bands

scores, all against the exact reference, no humans needed:
    data recovered   spearman rank corr between what i get back from the frame and the moment0 map.
                     rank because log/asinh keep the order but change ratios, so rank only
                     catches the ops that scramble order. pearson + rmse logged too
    structure kept   ssim between display normalized reference and recovered map, 7 px window,
                     plus the same at 2x downsample
    flux visible     share of the real flux (sky mask) whose rendered value is at least
                     vis_thresh of the frame max

controls put a ruler next to every number, see controls() and bands_from_controls().
the full spec with all the choices is in docs/metrics.md
"""
import numpy as np
from scipy import ndimage
from scipy.stats import spearmanr, pearsonr
from skimage.metrics import structural_similarity

from .render import norm_disp
from .operators import colormap
from .decode import invert_colormap, display_degrade


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


def structure_kept(ref01, out01, win=7):
    s1 = float(structural_similarity(ref01, out01, data_range=1.0, win_size=win))
    a = ndimage.zoom(ref01, 0.5, order=1)
    b = ndimage.zoom(out01, 0.5, order=1)
    s2 = float(structural_similarity(a, b, data_range=1.0, win_size=win))
    return dict(ssim=s1, ssim_2x=s2)


def flux_visible(ref01, out01, mask, vis_thresh=0.02):
    """share of the real flux still visible. also the old oct 27 version (20% of max)"""
    sig = mask if mask is not None else ref01 > 0.2
    vis = (out01 >= vis_thresh) & sig
    legacy_sig = ref01 > 0.2
    legacy_vis = (out01 > 0.2) & legacy_sig
    return dict(flux=float(ref01[vis].sum() / (ref01[sig].sum() + 1e-12)),
                flux_legacy20=float(ref01[legacy_vis].sum() / (ref01[legacy_sig].sum() + 1e-12)))


def score_frame(m0, ref01, recovered, mask, vis_thresh=0.02):
    """all scores for one frame. recovered is physical units, gets display normalized here"""
    out01 = norm_disp(recovered)
    s = {}
    s["data"] = data_recovered(m0, recovered, mask)
    s["structure"] = structure_kept(ref01, out01)
    s["flux"] = flux_visible(ref01, out01, mask, vis_thresh)
    # the 3 headline numbers flat, for tables
    s["headline"] = dict(data_recovered=s["data"]["mask"]["spearman"] if "mask" in s["data"] else s["data"]["all"]["spearman"],
                         structure_kept=s["structure"]["ssim"], flux_visible=s["flux"]["flux"])
    return s


def flip_score(rgb_ref, rgb_test):
    """nvidia FLIP mean error (0 = identical), None if the package is missing"""
    try:
        import flip_evaluator as flip
        _, mean_err, _ = flip.evaluate(rgb_ref.astype(np.float32), rgb_test.astype(np.float32), "LDR")
        return float(mean_err)
    except Exception:
        return None


# ------------------------------------------------------------------ controls and bands
def controls(m0, ref, mask, beam_px=2.0, n_seeds=100, cmap="gray", decoder=None):
    """score some reference frames that bracket what any operator can possibly do

    ceiling      reference + 8bit + display noise, n_seeds seeds (best you can get)
    beam_blur    reference blurred by 2x the beam, a loss that means something physically
    noise_only   a frame of just noise
    shuffled     reference with pixels shuffled
    random_ramp  reference through an unknown monotone colormap decoded as gray
    """
    decoder = decoder or {}
    ref01 = norm_disp(ref)
    scale = float(np.percentile(ref, 99.8)) + 1e-12
    rows = {}

    rho, ssim, flux = [], [], []
    for seed in range(n_seeds):
        rgb = colormap(ref01, cmap)
        rec01 = invert_colormap(rgb, cmap, seed=seed, **{k: v for k, v in decoder.items() if k in ("quantize", "noise_sigma")})
        s = score_frame(m0, ref01, rec01 * scale, mask)
        rho.append(s["headline"]["data_recovered"]); ssim.append(s["headline"]["structure_kept"]); flux.append(s["headline"]["flux_visible"])
    rows["ceiling"] = dict(data_recovered=float(np.percentile(rho, 5)), structure_kept=float(np.percentile(ssim, 5)),
                           flux_visible=float(np.percentile(flux, 5)), note="5th percentile over %d seeds" % n_seeds,
                           data_recovered_median=float(np.median(rho)), structure_kept_median=float(np.median(ssim)))

    blurred = ndimage.gaussian_filter(ref, 2.0 * beam_px)
    rows["beam_blur"] = dict(**score_frame(m0, ref01, blurred, mask)["headline"], note="reference blurred by 2x the beam (%.1f px)" % beam_px)

    rng = np.random.default_rng(0)
    noise = np.abs(rng.normal(0, 1, ref.shape)) * scale * 0.3
    rows["noise_only"] = dict(**score_frame(m0, ref01, noise, mask)["headline"], note="pure noise frame")

    shuffled = ref.ravel().copy(); rng.shuffle(shuffled); shuffled = shuffled.reshape(ref.shape)
    rows["shuffled"] = dict(**score_frame(m0, ref01, shuffled, mask)["headline"], note="reference pixels permuted")

    # unknown monotone ramp: gamma warped gray decoded like it was linear gray
    warped = colormap(ref01 ** 0.5, "gray")
    rec01 = invert_colormap(warped, "gray", seed=0)
    rows["random_ramp"] = dict(**score_frame(m0, ref01, rec01 * scale, mask)["headline"], note="gray with gamma 0.5, decoded as linear gray")
    return rows


def bands_from_controls(ctrl):
    """preserving = at/above the ceiling 5th pct, conditional = down to beam blur, distorting = below"""
    return dict(preserving_min=ctrl["ceiling"]["data_recovered"],
                conditional_min=ctrl["beam_blur"]["data_recovered"],
                structure_preserving_min=ctrl["ceiling"]["structure_kept"],
                structure_conditional_min=ctrl["beam_blur"]["structure_kept"])


def classify(value, bands, key="data"):
    lo = bands["conditional_min"] if key == "data" else bands["structure_conditional_min"]
    hi = bands["preserving_min"] if key == "data" else bands["structure_preserving_min"]
    if value >= hi:
        return "preserving"
    if value >= lo:
        return "conditional"
    return "distorting"
