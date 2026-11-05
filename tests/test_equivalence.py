"""the whole project sits on this one: plain render == moment0 map.
if someone touches render.py and this fails, no more zero point.
runs on every real cube in data/ (l1448 + the alma disk), the fake disk has its own test"""
import glob
import os
import numpy as np
import pytest

from cinecube.io import load_cube, moment0, peak_intensity
from cinecube.render import render

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
CUBES = sorted(p for p in glob.glob(os.path.join(DATA, "*.fits")) if "synthetic" not in p)


@pytest.fixture(scope="module", params=CUBES, ids=[os.path.basename(p) for p in CUBES])
def cube(request):
    return load_cube(request.param)


def test_there_are_cubes():
    assert any("l1448" in p for p in CUBES)


def test_plain_render_equals_moment0(cube):
    m0 = moment0(cube)
    ref = render(cube.T, cube.dv)
    assert ref.shape == m0.shape
    assert np.max(np.abs(ref - m0)) < 1e-10 * max(np.max(np.abs(m0)), 1.0)


def test_cube_is_in_K_and_kms(cube):
    assert cube.dv > 0 and np.isfinite(cube.T).all()
    assert cube.sigma > 0
    assert cube.valid.shape == cube.T.shape[1:]
    assert cube.beam_fwhm_px is None or cube.beam_fwhm_px > 0


def test_mip_equals_peak_intensity(cube):
    assert np.allclose(render(cube.T, cube.dv, composite="mip"), peak_intensity(cube))


def test_absorb_with_zero_kappa_is_additive(cube):
    a = render(cube.T, cube.dv, composite="absorb", kappa=0.0)
    b = render(cube.T, cube.dv)
    assert np.allclose(a, b)


def test_orbit_zero_is_identity(cube):
    assert np.allclose(render(cube.T, cube.dv, theta_deg=0.0, aspect=1.0), render(cube.T, cube.dv))
