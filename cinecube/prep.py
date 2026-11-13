import argparse
import json
import os

import numpy as np


def line_channels(sc, nchan, box=128):
    nv, ny, nx = sc.shape
    y0, x0 = ny // 2, nx // 2
    sub = sc[:, y0 - box // 2:y0 + box // 2, x0 - box // 2:x0 + box // 2]
    spec = np.nansum(sub.unmasked_data[:].value, axis=(1, 2))
    on = np.where(spec > 0.05 * spec.max())[0]
    mid = int(round(0.5 * (on[0] + on[-1])))
    lo = max(0, mid - nchan // 2)
    hi = min(nv, lo + nchan)
    lo = max(0, hi - nchan)
    return lo, hi, spec


def block_mean(a, f):
    nv, ny, nx = a.shape
    ny2, nx2 = ny // f, nx // f
    a = a[:, :ny2 * f, :nx2 * f].reshape(nv, ny2, f, nx2, f)
    return np.nanmean(a, axis=(2, 4))


def prep(path, out, size=256, nchan=128, down=2, center=None, doi=None, file_id=None, cite=None, name=None, beam_arcsec=None):
    from spectral_cube import SpectralCube
    from astropy.io import fits
    import astropy.units as u

    sc = SpectralCube.read(path)
    if hasattr(sc, "stokes_data"):
        sc = sc.stokes_data[list(sc.components)[0]] if hasattr(sc, "components") else sc
    ctype3_in = str(sc.header.get("CTYPE3"))
    rest = sc.header.get("RESTFRQ") or sc.header.get("RESTFREQ")
    if sc.spectral_axis.unit.is_equivalent(u.Hz):
        sc = sc.with_spectral_unit(u.km / u.s, velocity_convention="radio", rest_value=rest * u.Hz)
    else:
        sc = sc.with_spectral_unit(u.km / u.s)
    nv, ny, nx = sc.shape
    lo, hi, spec = line_channels(sc, nchan)
    if center is None:
        center = (ny // 2, nx // 2)
    cy, cx = center
    half = size * down // 2
    y0, y1 = max(0, cy - half), min(ny, cy + half)
    x0, x1 = max(0, cx - half), min(nx, cx + half)
    sub = sc[lo:hi, y0:y1, x0:x1]
    sub.allow_huge_operations = True
    unit_in = str(sub.unit)
    if "Jy" in unit_in:
        sub = sub.to(u.K)
    T = sub.unmasked_data[:].value.astype(np.float64)
    if down > 1:
        T = block_mean(T, down)
    T = T.astype(np.float32)
    v = sub.spectral_axis.to(u.km / u.s).value
    dv = float(np.median(np.diff(v)))

    try:
        bmaj = float(np.median([b.major.to("deg").value for b in sub.beams]))
        bmin = float(np.median([b.minor.to("deg").value for b in sub.beams]))
        bpa = float(np.median([b.pa.to("deg").value for b in sub.beams]))
    except Exception:
        bmaj, bmin, bpa = sc.header.get("BMAJ"), sc.header.get("BMIN"), sc.header.get("BPA")
    if not bmaj and beam_arcsec:
        bmaj = bmin = beam_arcsec / 3600.0
        bpa = 0.0

    h0 = sc.header
    h = fits.Header()
    h["BUNIT"] = "K"
    h["CTYPE1"], h["CTYPE2"] = h0["CTYPE1"], h0["CTYPE2"]
    h["CUNIT1"], h["CUNIT2"] = "deg", "deg"
    h["CDELT1"], h["CDELT2"] = h0["CDELT1"] * down, h0["CDELT2"] * down
    h["CRPIX1"] = (h0["CRPIX1"] - 1 - x0 - (down - 1) / 2) / down + 1
    h["CRPIX2"] = (h0["CRPIX2"] - 1 - y0 - (down - 1) / 2) / down + 1
    h["CRVAL1"], h["CRVAL2"] = h0["CRVAL1"], h0["CRVAL2"]
    h["CTYPE3"], h["CUNIT3"], h["CRPIX3"], h["CRVAL3"], h["CDELT3"] = "VRAD", "km/s", 1.0, float(v[0]), dv
    h["SPECSYS"] = h0.get("SPECSYS", "LSRK")
    if rest:
        h["RESTFRQ"] = float(rest)
    if bmaj:
        h["BMAJ"], h["BMIN"], h["BPA"] = bmaj, bmin, bpa
    h["OBJECT"] = name or h0.get("OBJECT", "") or os.path.basename(path).split("_")[0]
    h["TELESCOP"] = h0.get("TELESCOP", "")
    h["HISTORY"] = "cinecube.prep from %s" % os.path.basename(path)
    h["HISTORY"] = "channels %d:%d, pixels y %d:%d x %d:%d, block mean %dx%d" % (lo, hi, y0, y1, x0, x1, down, down)
    h["HISTORY"] = "unit in %s -> K via the beam (spectral-cube), FREQ -> VRAD km/s radio" % unit_in
    if doi:
        h["HISTORY"] = "source doi:%s file %s" % (doi, file_id)
    if beam_arcsec and not sc.header.get("BMAJ"):
        h["HISTORY"] = "beam %.2f arcsec from the survey paper, the file had none" % beam_arcsec
    fits.PrimaryHDU(T, header=h).writeto(out, overwrite=True)

    prov = dict(source_file=os.path.basename(path), dataset_doi=doi, file_id=file_id, citation=cite,
                shape_in=[int(nv), int(ny), int(nx)], shape_out=list(T.shape), unit_in=unit_in, unit_out="K",
                spectral_in=ctype3_in, spectral_out="VRAD km/s radio", restfrq_hz=float(rest) if rest else None,
                channels=[int(lo), int(hi)], pixels_y=[int(y0), int(y1)], pixels_x=[int(x0), int(x1)], block_mean=down,
                pixel_arcsec_in=abs(h0["CDELT2"]) * 3600, pixel_arcsec_out=abs(h0["CDELT2"]) * 3600 * down,
                beam_arcsec=bmaj * 3600 if bmaj else None, beam_fwhm_px=(bmaj / abs(h["CDELT2"])) if bmaj else None,
                dv_kms=dv, v_kms=[float(v[0]), float(v[-1])])
    json.dump(prov, open(out.replace(".fits", "_prep.json"), "w"), indent=1)
    print("wrote %s %s K, dv %.3f km/s, beam %.2f px, v %.2f..%.2f" % (out, T.shape, dv, prov["beam_fwhm_px"] or -1, v[0], v[-1]))
    return prov


def main(argv=None):
    ap = argparse.ArgumentParser(description="crop + convert a big archive cube into a small working cube")
    ap.add_argument("--in", dest="path", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, default=256, help="output pixels per side")
    ap.add_argument("--nchan", type=int, default=128)
    ap.add_argument("--down", type=int, default=2, help="block mean factor")
    ap.add_argument("--center", type=int, nargs=2, default=None, help="y x pixel of the object in the input, default image centre")
    ap.add_argument("--doi"); ap.add_argument("--file-id"); ap.add_argument("--cite"); ap.add_argument("--name")
    ap.add_argument("--beam-arcsec", type=float, default=None, help="beam fwhm if the file has none (things: from the survey table)")
    a = ap.parse_args(argv)
    prep(a.path, a.out, a.size, a.nchan, a.down, tuple(a.center) if a.center else None, a.doi, a.file_id, a.cite, a.name, a.beam_arcsec)


if __name__ == "__main__":
    main()
