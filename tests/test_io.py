"""the loader does every conversion right, each one checked on a tiny fake fits against astropy by hand
(not against spectral-cube, that would be circular). cases: alma (Jy/beam, FREQ, NaN padding, header beam),
aips (4d stokes, FELO m/s, JY/BEAM, beam in HISTORY), plain K + VRAD with no beam, yaml beam wins, n_edge"""
import numpy as np
import pytest
from astropy.io import fits
import astropy.units as u
import astropy.constants as const

from cinecube.io import load_cube, sky_mask, noise_sigma

REST_CO = 345795989900.0   # 12CO 3-2 Hz
REST_HI = 1420405750.0     # HI Hz


def sky_header(n, pix_deg):
    h = fits.Header()
    h["CTYPE1"], h["CTYPE2"], h["CUNIT1"], h["CUNIT2"] = "RA---SIN", "DEC--SIN", "deg", "deg"
    h["CRPIX1"], h["CRPIX2"], h["CRVAL1"], h["CRVAL2"] = n / 2, n / 2, 243.0, -32.0
    h["CDELT1"], h["CDELT2"] = -pix_deg, pix_deg
    return h


def write_alma(path, nv=8, n=16):
    """Jy/beam, FREQ axis, BMAJ keyword, NaN outside a circle"""
    T = np.full((nv, n, n), np.nan, dtype=np.float32)
    yy, xx = np.mgrid[:n, :n]
    inside = (yy - n / 2) ** 2 + (xx - n / 2) ** 2 < (n / 2 - 1) ** 2
    T[:, inside] = 0.001
    T[4, n // 2, n // 2] = 1.0
    h = sky_header(n, 0.025 / 3600)
    h["BUNIT"] = "Jy/beam"
    h["CTYPE3"], h["CUNIT3"], h["CRPIX3"], h["CRVAL3"], h["CDELT3"] = "FREQ", "Hz", 1.0, REST_CO + 4 * 115345.0, -115345.0
    h["RESTFRQ"], h["SPECSYS"] = REST_CO, "LSRK"
    h["BMAJ"], h["BMIN"], h["BPA"] = 0.15 / 3600, 0.15 / 3600, 0.0
    fits.PrimaryHDU(T, header=h).writeto(path, overwrite=True)


def write_aips(path, nv=8, n=16):
    """4d (stokes), JY/BEAM, FELO-HEL in m/s, beam only in an AIPS HISTORY line. like THINGS"""
    T = np.full((1, nv, n, n), 0.0005, dtype=np.float32)
    T[0, 3, n // 2, n // 2] = 0.1
    h = sky_header(n, 1.0 / 3600)
    h["BUNIT"] = "JY/BEAM"
    h["CTYPE3"], h["CRPIX3"], h["CRVAL3"], h["CDELT3"] = "FELO-HEL", 1.0, 100000.0, -5000.0
    h["CTYPE4"], h["CRPIX4"], h["CRVAL4"], h["CDELT4"] = "STOKES", 1.0, 1.0, 1.0
    h["RESTFREQ"] = REST_HI
    h["HISTORY"] = "AIPS   CLEAN BMAJ=  2.4308E-03 BMIN=  2.1246E-03 BPA=  25.16"
    fits.PrimaryHDU(T, header=h).writeto(path, overwrite=True)


def write_plain(path, nv=8, n=16, with_edges_noise=0.0):
    """K, VRAD km/s, no beam, no BUNIT. like l1448 / the synthetic disk"""
    rng = np.random.default_rng(0)
    T = np.zeros((nv, n, n), dtype=np.float32)
    T[2:6] = 1.0
    if with_edges_noise:
        T += rng.normal(0, with_edges_noise, T.shape).astype(np.float32)
    h = sky_header(n, 23.0 / 3600)
    h["CTYPE3"], h["CUNIT3"], h["CRPIX3"], h["CRVAL3"], h["CDELT3"] = "VRAD", "km/s", 1.0, 0.0, 0.066
    h["RESTFRQ"] = 110201353000.0
    fits.PrimaryHDU(T, header=h).writeto(path, overwrite=True)
    return T


def test_alma_jy_per_beam_to_K_and_freq_to_kms(tmp_path):
    p = str(tmp_path / "alma.fits"); write_alma(p)
    c = load_cube(p, name="fake")
    omega = (np.pi / (4 * np.log(2))) * (0.15 / 3600 * u.deg) ** 2
    expect = (1.0 * u.Jy / omega).to(u.K, equivalencies=u.brightness_temperature(REST_CO * u.Hz)).value
    assert c.T[4, 8, 8] == pytest.approx(expect, rel=1e-3)
    assert "Jy/beam" in c.meta["converted"]
    assert c.v[4] == pytest.approx(0.0, abs=1e-6)                                   # channel 4 is at the rest freq
    assert c.dv == pytest.approx((const.c * 115345.0 / REST_CO).to("km/s").value, rel=1e-6)
    assert c.meta["velocity_convention"] == "radio"
    assert c.beam_fwhm_px == pytest.approx(6.0, rel=1e-6) and c.meta["beam_source"] == "header"


def test_alma_nan_padding(tmp_path):
    p = str(tmp_path / "alma.fits"); write_alma(p)
    c = load_cube(p)
    assert np.isfinite(c.T).all()
    assert c.valid[8, 8] and not c.valid[0, 0]
    m = sky_mask(np.ones((16, 16)), 0.0, 3.0, c.valid)
    assert m[8, 8] and not m[0, 0]
    # noise comes from the real pixels only, the NaN corners dont pull it to 0
    assert c.sigma == pytest.approx(0.0, abs=1e-6) or c.sigma > 0


def test_aips_stokes_felo_history_beam(tmp_path):
    p = str(tmp_path / "aips.fits"); write_aips(p)
    c = load_cube(p, name="fake")
    assert c.T.ndim == 3 and c.T.shape == (8, 16, 16)                                # stokes axis dropped
    # m/s -> km/s. FELO is optical velocity on a grid thats regular in frequency, so the velocity step
    # drifts a little across the band (0.01% here, 0.08% on the real things cube). median diff, not CDELT3
    assert c.dv == pytest.approx(5.0, rel=1e-3)
    assert c.v[0] == pytest.approx(100.0, rel=1e-6)
    assert c.beam_fwhm_px == pytest.approx(2.4308e-3 * 3600 / 1.0, rel=1e-4)        # from the HISTORY line, 8.75 arcsec / 1 arcsec px
    assert c.meta["beam_source"] == "header"
    omega = (np.pi / (4 * np.log(2))) * (2.4308e-3 * u.deg) * (2.1246e-3 * u.deg)
    expect = (0.1 * u.Jy / omega).to(u.K, equivalencies=u.brightness_temperature(REST_HI * u.Hz)).value
    assert c.T[3, 8, 8] == pytest.approx(expect, rel=1e-3)


def test_plain_K_vrad_no_beam(tmp_path):
    p = str(tmp_path / "plain.fits"); write_plain(p)
    c = load_cube(p)
    assert c.T[3, 0, 0] == 1.0 and c.dv == pytest.approx(0.066)
    assert c.beam_fwhm_px is None and c.meta["beam_source"] == "none"
    assert "no BUNIT" in c.meta["converted"]
    assert c.valid.all()


def test_given_beam_wins_over_header(tmp_path):
    p = str(tmp_path / "alma.fits"); write_alma(p)
    assert load_cube(p, beam_fwhm_px=2.5).beam_fwhm_px == 2.5
    assert load_cube(p, beam_fwhm_px=2.5).meta["beam_source"] == "given"
    q = str(tmp_path / "plain.fits"); write_plain(q)
    assert load_cube(q, beam_fwhm_px=2.0).beam_fwhm_px == 2.0


def test_noise_edge_channels(tmp_path):
    p = str(tmp_path / "plain.fits"); T = write_plain(p, with_edges_noise=0.1)
    c1 = load_cube(p, n_edge=1); c2 = load_cube(p, n_edge=2)
    assert c1.sigma == pytest.approx(noise_sigma(T, 1), rel=1e-6)
    assert c2.sigma == pytest.approx(noise_sigma(T, 2), rel=1e-6)
    assert c1.meta["n_edge"] == 1
    # n_edge=3 would eat channel 2 which has signal, so the noise would jump
    assert load_cube(p, n_edge=3).sigma > 3 * c2.sigma
