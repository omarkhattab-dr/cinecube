"""decoder gets the reference back, scores do the right thing at both ends"""
import os
import numpy as np
import pytest

from cinecube.io import load_cube, moment0, sky_mask
from cinecube.render import render, norm_disp, disp_scale
from cinecube.operators import colormap, apply_operator, OPERATORS
from cinecube.decode import invert_colormap, decode_frame
from cinecube.metrics import score_frame, classify

CUBE = os.path.join(os.path.dirname(__file__), "..", "data", "l1448_13co.fits")


@pytest.fixture(scope="module")
def setup():
    cube = load_cube(CUBE)
    m0 = moment0(cube)
    ref = render(cube.T, cube.dv)
    mask = sky_mask(m0, cube.sigma_m0)
    return cube, m0, ref, mask


@pytest.mark.parametrize("cmap", ["gray", "inferno", "viridis"])
def test_reference_round_trip(setup, cmap):
    cube, m0, ref, mask = setup
    ref01 = norm_disp(ref)
    rec01 = invert_colormap(colormap(ref01, cmap), cmap)
    s = score_frame(m0, ref01, rec01 * disp_scale(ref), mask)
    assert s["headline"]["data_recovered"] > 0.98
    assert s["headline"]["structure_kept"] > 0.95
    assert s["headline"]["flux_visible"] > 0.98


def test_shuffled_scores_near_zero(setup):
    cube, m0, ref, mask = setup
    rng = np.random.default_rng(0)
    shuffled = ref.ravel().copy(); rng.shuffle(shuffled); shuffled = shuffled.reshape(ref.shape)
    s = score_frame(m0, norm_disp(ref), shuffled, mask)
    assert abs(s["headline"]["data_recovered"]) < 0.1


def test_every_operator_runs_and_decodes(setup):
    cube, m0, ref, mask = setup
    for name in OPERATORS:
        fr = apply_operator(cube, name)
        rec, rec01 = decode_frame(fr)
        assert rec.shape == m0.shape, name
        assert np.isfinite(rec).all(), name


def test_classify_bands():
    bands = dict(preserving_min=0.95, conditional_min=0.80, structure_preserving_min=0.9, structure_conditional_min=0.5)
    assert classify(0.99, bands) == "preserving"
    assert classify(0.9, bands) == "conditional"
    assert classify(0.5, bands) == "distorting"
