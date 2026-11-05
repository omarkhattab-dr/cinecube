"""
io.py - loading the cube, moment maps, noise, sky mask

moment maps come from spectral-cube on purpose. the thing i score against should not
come out of my own renderer.

cubes come in 2 flavours:
  single dish (l1448)   K, velocity axis already, no beam in the header
  interferometer (alma) Jy/beam, FREQ axis, a beam per channel, NaN outside the imaged area
load_cube() turns both into the same thing: T in K, v in km/s (radio convention), a beam in px,
a valid mask for the NaN padding. everything it did is in cube.meta so the frame json can say it
"""
from dataclasses import dataclass, field
import hashlib
import warnings

import numpy as np

warnings.filterwarnings("ignore")


@dataclass
class Cube:
    """ppv cube in K

    T       array [v, y, x] in K, nans -> 0
    dv      channel width km/s
    v       velocity axis km/s
    sigma   noise per channel (K), from the empty end channels
    path    where it came from
    name    short label for file names
    valid   [y, x] bool, False where the cube is NaN padding (outside the alma image), sky mask uses it
    beam_fwhm_px  beam fwhm in pixels (None if the header has no beam and nobody passed one)
    meta    what load_cube did: input unit, input spectral axis, rest freq, pixel size, beam
    sc      the SpectralCube object, kept around for the moment maps
    """
    T: np.ndarray
    dv: float
    v: np.ndarray
    sigma: float
    path: str
    name: str
    valid: np.ndarray = None
    beam_fwhm_px: float = None
    meta: dict = field(default_factory=dict)
    sc: object = field(repr=False, default=None)

    @property
    def shape(self):
        return self.T.shape

    @property
    def sigma_m0(self):
        """noise of the moment0 map if you sum all channels: sigma * dv * sqrt(nchan)"""
        return self.sigma * self.dv * np.sqrt(self.T.shape[0])


def load_cube(path, name=None, n_edge=3, beam_fwhm_px=None):
    """read a fits cube with spectral-cube, give back a Cube in K and km/s

    beam_fwhm_px: pass it when the header has no beam (l1448). header beam wins when both exist
    """
    from spectral_cube import SpectralCube
    import astropy.units as u

    sc = SpectralCube.read(path)
    meta = dict(unit_in=str(sc.unit), spectral_in=str(sc.spectral_axis.unit), ctype3=str(sc.wcs.wcs.ctype[2]))

    # spectral axis -> km/s. alma gives FREQ, so radio convention with the rest freq from the header
    rest = sc.header.get("RESTFRQ") or sc.header.get("RESTFREQ")
    if sc.spectral_axis.unit.is_equivalent(u.Hz):
        if not rest:
            raise ValueError("%s has a frequency axis and no RESTFRQ, cant make velocities" % path)
        sc = sc.with_spectral_unit(u.km / u.s, velocity_convention="radio", rest_value=rest * u.Hz)
        meta["velocity_convention"] = "radio"
    else:
        sc = sc.with_spectral_unit(u.km / u.s)
    meta["restfrq_hz"] = float(rest) if rest else None

    # brightness -> K. Jy/beam needs the beam and the frequency, spectral-cube does that per channel
    if sc.unit.is_equivalent(u.Jy / u.beam) or "Jy" in str(sc.unit):
        sc = sc.to(u.K)
        meta["converted"] = "Jy/beam -> K via the beam (spectral-cube .to(K))"
    elif not sc.unit.is_equivalent(u.K):
        meta["converted"] = "unit %s left as is, treated as K" % sc.unit

    raw = sc.unmasked_data[:].value.astype(np.float64)
    valid = np.isfinite(raw).any(axis=0)
    T = np.nan_to_num(raw)
    v = sc.spectral_axis.value
    dv = float(abs(np.median(np.diff(v))))

    # pixel size + beam. multi beam cubes (alma) -> median beam
    pix = pixel_arcsec(sc)
    meta["pixel_arcsec"] = pix
    bmaj = header_beam_arcsec(sc)
    if bmaj is not None and pix:
        beam_fwhm_px = bmaj / pix
        meta["beam_arcsec"] = bmaj
        meta["beam_source"] = "header"
    elif beam_fwhm_px is not None:
        meta["beam_source"] = "given"
    meta["beam_fwhm_px"] = beam_fwhm_px

    sigma = noise_sigma(T, n_edge, valid)
    if name is None:
        name = path.split("/")[-1].replace(".fits", "")
    return Cube(T=T, dv=dv, v=v, sigma=sigma, path=path, name=name, valid=valid, beam_fwhm_px=beam_fwhm_px, meta=meta, sc=sc)


def pixel_arcsec(sc):
    """pixel size in arcsec from the wcs, None if the wcs is not sky"""
    try:
        from astropy.wcs.utils import proj_plane_pixel_scales
        scales = proj_plane_pixel_scales(sc.wcs.celestial)
        return float(abs(scales[0]) * 3600)
    except Exception:
        return None


def header_beam_arcsec(sc):
    """BMAJ in arcsec. single beam from the header, or the median of a beam table. None if neither"""
    try:
        if hasattr(sc, "beams") and sc.beams is not None:
            return float(np.median([b.major.to("arcsec").value for b in sc.beams]))
        if hasattr(sc, "beam") and sc.beam is not None:
            return float(sc.beam.major.to("arcsec").value)
    except Exception:
        pass
    b = sc.header.get("BMAJ")
    return float(b) * 3600 if b else None


def noise_sigma(T, n_edge=3, valid=None):
    """noise from the n_edge empty channels at both ends of the band, real pixels only"""
    sel = valid if valid is not None else np.ones(T.shape[1:], dtype=bool)
    edges = np.concatenate([T[:n_edge][:, sel].ravel(), T[-n_edge:][:, sel].ravel()])
    return float(np.std(edges))


def moment0(cube):
    """total emission K km/s. from spectral-cube not from me"""
    import astropy.units as u
    m0 = cube.sc.with_spectral_unit(u.km / u.s).moment(order=0)
    return np.nan_to_num(m0.value.astype(np.float64))


def moment1(cube):
    """mean velocity weighted by intensity, km/s"""
    import astropy.units as u
    m1 = cube.sc.with_spectral_unit(u.km / u.s).moment(order=1)
    return np.nan_to_num(m1.value.astype(np.float64))


def peak_intensity(cube):
    """peak along v, in K. the MIP render should match this"""
    return cube.T.max(axis=0)


def sky_mask(m0, sigma_m0, k=3.0, valid=None):
    """pixels where moment0 is real signal: m0 > k * sigma_m0, and not NaN padding"""
    m = m0 > k * sigma_m0
    if valid is not None:
        m &= valid
    return m


def cube_hash(path):
    """short hash of the file so every result knows which cube it came from"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]
