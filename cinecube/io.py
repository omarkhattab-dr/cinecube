"""
io.py - loading the cube, moment maps, noise, sky mask

moment maps come from spectral-cube on purpose. the thing i score against should not
come out of my own renderer.
"""
from dataclasses import dataclass, field
import hashlib
import warnings

import numpy as np

warnings.filterwarnings("ignore")


@dataclass
class Cube:
    """ppv cube in K

    T      array [v, y, x] in K, nans -> 0
    dv     channel width km/s
    v      velocity axis km/s
    sigma  noise per channel (K), from the empty end channels
    path   where it came from
    name   short label for file names
    sc     the SpectralCube object, kept around for the moment maps
    """
    T: np.ndarray
    dv: float
    v: np.ndarray
    sigma: float
    path: str
    name: str
    sc: object = field(repr=False, default=None)

    @property
    def shape(self):
        return self.T.shape

    @property
    def sigma_m0(self):
        """noise of the moment0 map if you sum all channels: sigma * dv * sqrt(nchan)"""
        return self.sigma * self.dv * np.sqrt(self.T.shape[0])


def load_cube(path, name=None, n_edge=3):
    """read a fits cube with spectral-cube, give back a Cube in K and km/s"""
    from spectral_cube import SpectralCube
    import astropy.units as u

    sc = SpectralCube.read(path).with_spectral_unit(u.km / u.s)
    T = np.nan_to_num(sc.unmasked_data[:].value.astype(np.float64))
    v = sc.spectral_axis.value
    dv = float(abs(np.median(np.diff(v))))
    sigma = noise_sigma(T, n_edge)
    if name is None:
        name = path.split("/")[-1].replace(".fits", "")
    return Cube(T=T, dv=dv, v=v, sigma=sigma, path=path, name=name, sc=sc)


def noise_sigma(T, n_edge=3):
    """noise from the n_edge empty channels at both ends of the band"""
    edges = np.concatenate([T[:n_edge].ravel(), T[-n_edge:].ravel()])
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


def sky_mask(m0, sigma_m0, k=3.0):
    """pixels where moment0 is real signal: m0 > k * sigma_m0"""
    return m0 > k * sigma_m0


def cube_hash(path):
    """short hash of the file so every result knows which cube it came from"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]
