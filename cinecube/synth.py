"""
synth.py - fake keplerian disk where i know the 3d truth

on a real cube nobody knows the true depth. here i do. the disk lives on a 3d sky grid
(x, y, z with z along the line of sight), every voxel has a density and a line of sight
velocity, and the ppv cube is sum over z of density * gaussian line at that velocity.
the truth (density + velocity on the grid) gets saved next to the cube for the index.

    python -m cinecube.synth --out data/synthetic_disk --inc 45

writes data/synthetic_disk.fits (spectral-cube can read it) + data/synthetic_disk_truth.npz.
moment0 = column density along z by construction, so the equivalence test holds here too
(tests/test_synth.py)
"""
import argparse
import json

import numpy as np
from scipy import ndimage


def keplerian_disk(nx=128, ny=128, nz=96, nv=64, dv=None, r_in=8.0, r_out=48.0, inc_deg=45.0, pa_deg=25.0,
                   h0=2.5, flare=0.3, v0=1.6, sigma_v=0.12, v_sys=0.0, peak_K=4.0, beam_fwhm_px=2.5,
                   noise_K=0.24, seed=0):
    """build the cube + truth. lengths in pixels, velocities km/s, brightness K

    density   surface density (r/r_in)^-1 between r_in and r_out with soft edges, gaussian in
              height, scale height h0 * (r/r_in)^flare
    velocity  keplerian, v_phi = v0 sqrt(r_in/r), line of sight = v_phi cos(phi) sin(i) + v_sys
    geometry  disk frame -> tilt by inclination about x -> rotate by PA about z (line of sight)
    dv=None picks a channel width so the band covers +-(v0 sin i) plus 4 line widths. pass dv to force
    inside r_in rotation is held at v0 (inner hole, not a singularity)
    """
    rng = np.random.default_rng(seed)
    i = np.deg2rad(inc_deg)
    if dv is None:
        dv = (2 * v0 * np.sin(i) + 8 * sigma_v) / nv
    pa = np.deg2rad(pa_deg)
    x = np.arange(nx) - nx / 2 + 0.5
    y = np.arange(ny) - ny / 2 + 0.5
    z = np.arange(nz) - nz / 2 + 0.5
    v = v_sys + (np.arange(nv) - nv / 2 + 0.5) * dv
    X, Y = np.meshgrid(x, y)  # [y, x]
    # undo the position angle in the sky plane
    xs = X * np.cos(pa) + Y * np.sin(pa)
    ys = -X * np.sin(pa) + Y * np.cos(pa)

    T = np.zeros((nv, ny, nx))
    rho_grid = np.zeros((nz, ny, nx))
    vlos_grid = np.zeros((nz, ny, nx))
    for k, zk in enumerate(z):
        # undo the inclination about x: sky (xs, ys, z) -> disk (xd, yd, zd)
        xd = xs
        yd = ys * np.cos(i) + zk * np.sin(i)
        zd = -ys * np.sin(i) + zk * np.cos(i)
        r = np.hypot(xd, yd) + 1e-9
        phi = np.arctan2(yd, xd)
        h = h0 * (r / r_in) ** flare
        sigma_r = (r / r_in) ** -1.0
        edge = 1.0 / (1.0 + np.exp(-(r - r_in) / 1.5)) * 1.0 / (1.0 + np.exp((r - r_out) / 3.0))
        rho = sigma_r * edge * np.exp(-0.5 * (zd / h) ** 2) / (np.sqrt(2 * np.pi) * h)
        vphi = v0 * np.sqrt(r_in / np.maximum(r, r_in))
        vlos = vphi * np.cos(phi) * np.sin(i) + v_sys
        rho_grid[k] = rho
        vlos_grid[k] = vlos
        line = np.exp(-0.5 * ((v[:, None, None] - vlos[None]) / sigma_v) ** 2) / (np.sqrt(2 * np.pi) * sigma_v)
        T += rho[None] * line * 1.0  # dz = 1 pixel
    # units: brightest channel peaks at peak_K, then beam, then noise
    T *= peak_K / T.max()
    rho_grid *= peak_K / (rho_grid.sum(axis=0).max() + 1e-12)  # column density in the same units as moment0
    if beam_fwhm_px > 0:
        s = beam_fwhm_px / 2.3548
        T = np.stack([ndimage.gaussian_filter(ch, s) for ch in T])
        rho_grid = np.stack([ndimage.gaussian_filter(sl, s) for sl in rho_grid])
    T_clean = T.copy()
    if noise_K > 0:
        T = T + rng.normal(0, noise_K, T.shape)
    truth = dict(rho=rho_grid, vlos=vlos_grid, v=v, T_clean=T_clean,
                 params=dict(nx=nx, ny=ny, nz=nz, nv=nv, dv=dv, r_in=r_in, r_out=r_out, inc_deg=inc_deg, pa_deg=pa_deg, h0=h0,
                             flare=flare, v0=v0, sigma_v=sigma_v, v_sys=v_sys, peak_K=peak_K, beam_fwhm_px=beam_fwhm_px, noise_K=noise_K, seed=seed))
    return T, v, truth


def write_fits(T, v, path, dv, pixel_arcsec=1.0):
    """write a cube spectral-cube can read, RA/Dec TAN axes + VRAD axis in km/s"""
    from astropy.io import fits
    nv, ny, nx = T.shape
    h = fits.Header()
    h["BUNIT"] = "K"
    h["CTYPE1"], h["CUNIT1"], h["CRPIX1"], h["CRVAL1"], h["CDELT1"] = "RA---TAN", "deg", nx / 2 + 0.5, 83.0, -pixel_arcsec / 3600
    h["CTYPE2"], h["CUNIT2"], h["CRPIX2"], h["CRVAL2"], h["CDELT2"] = "DEC--TAN", "deg", ny / 2 + 0.5, -5.0, pixel_arcsec / 3600
    h["CTYPE3"], h["CUNIT3"], h["CRPIX3"], h["CRVAL3"], h["CDELT3"] = "VRAD", "km/s", 1.0, float(v[0]), float(dv)
    h["SPECSYS"] = "LSRK"
    h["RESTFRQ"] = 110201353000.0  # 13CO 1-0 so spectral-cube can convert units
    h["OBJECT"] = "synthetic Keplerian disk (cinecube.synth)"
    fits.PrimaryHDU(T.astype(np.float32), header=h).writeto(path, overwrite=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="build the synthetic disk cube and its truth")
    ap.add_argument("--out", default="data/synthetic_disk", help="output stem (writes <stem>.fits and <stem>_truth.npz)")
    ap.add_argument("--inc", type=float, default=45.0)
    ap.add_argument("--pa", type=float, default=25.0)
    ap.add_argument("--nv", type=int, default=64)
    ap.add_argument("--size", type=int, default=128)
    ap.add_argument("--nz", type=int, default=96)
    ap.add_argument("--noise", type=float, default=0.24)
    ap.add_argument("--dv", type=float, default=None, help="channel width in km/s (default: fit the band to the disk)")
    a = ap.parse_args(argv)
    T, v, truth = keplerian_disk(nx=a.size, ny=a.size, nz=a.nz, nv=a.nv, dv=a.dv, inc_deg=a.inc, pa_deg=a.pa, noise_K=a.noise)
    write_fits(T, v, a.out + ".fits", truth["params"]["dv"])
    np.savez_compressed(a.out + "_truth.npz", rho=truth["rho"], vlos=truth["vlos"], v=truth["v"], T_clean=truth["T_clean"],
                        params=json.dumps(truth["params"]))
    print("wrote %s.fits %s and %s_truth.npz (rho %s)" % (a.out, T.shape, a.out, truth["rho"].shape))


if __name__ == "__main__":
    main()
