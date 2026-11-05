"""the loader does the alma conversions right: Jy/beam -> K through the beam, FREQ -> km/s radio,
NaN padding -> valid mask. checked against astropy on a tiny fake cube, not against spectral-cube"""
import numpy as np
import pytest
from astropy.io import fits
import astropy.units as u
import astropy.constants as const

from cinecube.io import load_cube, sky_mask

REST = 345795989900.0   # 12CO 3-2 Hz
BMAJ = 0.15 / 3600      # deg
PIX = 0.025 / 3600


def fake_alma_cube(path, nv=8, n=16):
    T = np.full((nv, n, n), np.nan, dtype=np.float32)
    yy, xx = np.mgrid[:n, :n]
    inside = (yy - n / 2) ** 2 + (xx - n / 2) ** 2 < (n / 2 - 1) ** 2   # alma images are NaN outside a circle
    T[:, inside] = 0.001                                                # 1 mJy/beam everywhere real
    T[4, n // 2, n // 2] = 1.0                                          # 1 Jy/beam in 1 voxel
    h = fits.Header()
    h["BUNIT"] = "Jy/beam"
    h["CTYPE1"], h["CTYPE2"], h["CUNIT1"], h["CUNIT2"] = "RA---SIN", "DEC--SIN", "deg", "deg"
    h["CRPIX1"], h["CRPIX2"], h["CRVAL1"], h["CRVAL2"] = n / 2, n / 2, 243.0, -32.0
    h["CDELT1"], h["CDELT2"] = -PIX, PIX
    h["CTYPE3"], h["CUNIT3"], h["CRPIX3"], h["CRVAL3"], h["CDELT3"] = "FREQ", "Hz", 1.0, REST + 4 * 115345.0, -115345.0
    h["RESTFRQ"], h["SPECSYS"] = REST, "LSRK"
    h["BMAJ"], h["BMIN"], h["BPA"] = BMAJ, BMAJ, 0.0
    fits.PrimaryHDU(T, header=h).writeto(path, overwrite=True)
    return T


def test_alma_conversions(tmp_path):
    p = str(tmp_path / "fake_alma.fits")
    raw = fake_alma_cube(p)
    c = load_cube(p, name="fake")
    # Jy/beam -> K: rayleigh jeans with the beam solid angle, done here with astropy by hand
    omega = (np.pi / (4 * np.log(2))) * (BMAJ * u.deg) ** 2
    expect = (1.0 * u.Jy / omega).to(u.K, equivalencies=u.brightness_temperature(REST * u.Hz)).value
    assert c.T[4, 8, 8] == pytest.approx(expect, rel=1e-3)
    assert "Jy/beam" in c.meta["converted"]
    # FREQ -> km/s radio: v = c (nu0 - nu) / nu0. channel 4 sits at the rest freq -> 0 km/s
    assert c.v[4] == pytest.approx(0.0, abs=1e-6)
    assert c.dv == pytest.approx((const.c * 115345.0 / REST).to("km/s").value, rel=1e-6)
    assert c.meta["velocity_convention"] == "radio"
    # beam from the header in px
    assert c.beam_fwhm_px == pytest.approx(6.0, rel=1e-6)
    # NaN padding is 0 in T and False in valid, and stays out of the sky mask
    assert np.isfinite(c.T).all()
    assert c.valid[8, 8] and not c.valid[0, 0]
    m = sky_mask(np.ones((16, 16)), 0.0, 3.0, c.valid)
    assert m[8, 8] and not m[0, 0]
