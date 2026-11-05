"""decoder gets the reference back, scores do the right thing at both ends, spec numbers hold"""
import os
import numpy as np
import pytest

from cinecube.io import load_cube, moment0, sky_mask
from cinecube.render import render, norm_disp, disp_scale
from cinecube.operators import colormap, apply_operator, OPERATORS
from cinecube.decode import invert_colormap, decode_frame, ramp_bins, zero_color_lab
from cinecube.metrics import score_frame, classify, controls, bands_from_controls, visible_mask

CUBE = os.path.join(os.path.dirname(__file__), "..", "data", "l1448_13co.fits")


@pytest.fixture(scope="module")
def setup():
    cube = load_cube(CUBE)
    m0 = moment0(cube)
    ref = render(cube.T, cube.dv)
    mask = sky_mask(m0, cube.sigma_m0)
    return cube, m0, ref, mask


def test_bins_follow_arc_length():
    # longer ramp = more readable levels. numbers from docs/metrics.md
    n = {cm: len(ramp_bins(cm)[0]) for cm in ("gray", "viridis", "inferno", "jet")}
    assert n["gray"] < n["viridis"] < n["inferno"] < n["jet"]
    assert 20 <= n["gray"] <= 32
    c01, _, _ = ramp_bins("gray")
    assert np.all(np.diff(c01) > 0)       # centers walk up the ramp


@pytest.mark.parametrize("cmap", ["gray", "inferno", "viridis"])
def test_reference_round_trip(setup, cmap):
    cube, m0, ref, mask = setup
    ref01 = norm_disp(ref)
    rgb = colormap(ref01, cmap)
    rec01 = invert_colormap(rgb, cmap)
    s = score_frame(m0, ref01, rec01 * disp_scale(ref), mask, rgb, zero_color_lab(cmap))
    assert s["headline"]["data_recovered"] > 0.99
    assert s["headline"]["structure_kept"] > 0.95
    assert s["headline"]["flux_visible"] > 0.95


def test_decoder_is_deterministic(setup):
    cube, m0, ref, mask = setup
    rgb = colormap(norm_disp(ref), "inferno")
    a = invert_colormap(rgb, "inferno"); b = invert_colormap(rgb, "inferno")
    assert np.array_equal(a, b)


def test_shuffled_scores_near_zero(setup):
    cube, m0, ref, mask = setup
    rng = np.random.default_rng(0)
    shuffled = ref.ravel().copy(); rng.shuffle(shuffled); shuffled = shuffled.reshape(ref.shape)
    s = score_frame(m0, norm_disp(ref), shuffled, mask)
    assert abs(s["headline"]["data_recovered"]) < 0.1


def test_flux_visible_sees_a_jnd():
    # a flat 2% gray is under 1 JND from black (invisible), 10% is well over
    zero = zero_color_lab("gray")
    assert not visible_mask(np.full((4, 4, 3), 0.02), zero).any()
    assert visible_mask(np.full((4, 4, 3), 0.10), zero).all()


def test_vignette_loses_flux(setup):
    cube, m0, ref, mask = setup
    fr = apply_operator(cube, "vignette", dict(strength=0.5))
    rec, _ = decode_frame(fr)
    s = score_frame(m0, norm_disp(ref), rec, mask, fr["rgb"], zero_color_lab(fr["cmap"]))
    assert s["headline"]["flux_visible"] < 0.999


def test_every_operator_runs_and_decodes(setup):
    cube, m0, ref, mask = setup
    for name in OPERATORS:
        fr = apply_operator(cube, name)
        rec, rec01 = decode_frame(fr)
        assert rec.shape == m0.shape, name
        assert np.isfinite(rec).all(), name


def test_controls_order(setup):
    # ceiling >= beam blur >= shuffled, bands come out of them
    cube, m0, ref, mask = setup
    c = controls(m0, ref, mask, beam_fwhm_px=2.0)
    assert c["ceiling"]["data_recovered"] >= c["beam_blur"]["data_recovered"] > c["shuffled"]["data_recovered"]
    assert c["ceiling"]["structure_kept"] >= c["beam_blur"]["structure_kept"] > c["shuffled"]["structure_kept"]
    b = bands_from_controls(c)
    assert b["preserving_min"] >= b["conditional_min"]
    assert classify(c["ceiling"]["data_recovered"], b) == "preserving"


def test_classify_bands():
    bands = dict(preserving_min=0.95, conditional_min=0.80, structure_preserving_min=0.9, structure_conditional_min=0.5)
    assert classify(0.99, bands) == "preserving"
    assert classify(0.9, bands) == "conditional"
    assert classify(0.5, bands) == "distorting"
