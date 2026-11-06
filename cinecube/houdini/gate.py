"""
gate.py - the zero point check for a production render. runs here, no houdini needed.

    python -m cinecube.houdini.gate --render renders/l1448_plain.exr --cube l1448
    python -m cinecube.houdini.gate --render renders/l1448_plain.exr --cube l1448 --samples 256 --step 0.5

takes the plain render (emission only, ortho camera down -z, 1 px per voxel, linear exr) and compares
it to the gate target = sum over z of the clipped density times dv (results/houdini/vdb/<key>_target.npy).
emission only rendering is linear so the 2 should be the same map up to 1 scale factor k. the fit is
least squares inside the sky mask. pass = max |k * render - target| inside the mask under 1% of the
target peak. writes results/houdini/gate_<key>.json + gate_<key>.png (render, target, deviation map).

orientation: an exr has row 0 at the top, our maps have row 0 at the bottom. the gate tries the 4
flips and keeps the one that fits best, and says which, so a flipped camera doesnt fail the gate for
the wrong reason. a transposed render (x and y swapped) is also tried.

render formats: .exr (R channel or luminance), .npy (float array), .png (8 or 16 bit, treated as linear,
only good for a rough look, use exr for the real gate)
"""
import argparse
import json
import os

import numpy as np

from ..io import load_cube, moment0, sky_mask


def read_render(path, channel="R"):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".npy":
        return np.load(path).astype(np.float64)
    if ext == ".exr":
        import OpenEXR
        try:                                            # openexr 3.x api
            with OpenEXR.File(path) as f:
                ch = f.channels()
                if channel in ch:
                    return np.asarray(ch[channel].pixels, dtype=np.float64)
                if "RGB" in ch:                           # interleaved rgb -> luminance like channel mean
                    return np.asarray(ch["RGB"].pixels, dtype=np.float64).mean(axis=-1)
                key = list(ch)[0]
                px = np.asarray(ch[key].pixels, dtype=np.float64)
                return px.mean(axis=-1) if px.ndim == 3 else px
        except AttributeError:                          # legacy 2.x api
            import Imath
            f = OpenEXR.InputFile(path)
            dw = f.header()["dataWindow"]
            w, h = dw.max.x - dw.min.x + 1, dw.max.y - dw.min.y + 1
            buf = f.channel(channel, Imath.PixelType(Imath.PixelType.FLOAT))
            return np.frombuffer(buf, dtype=np.float32).reshape(h, w).astype(np.float64)
    from PIL import Image
    im = Image.open(path)
    arr = np.asarray(im, dtype=np.float64)
    if arr.ndim == 3:
        arr = arr[..., :3].mean(axis=-1)
    return arr / (65535.0 if im.mode.startswith("I;16") else 255.0)


def write_exr(path, arr):
    """for tests and for people who want to look at the target in nuke/houdini"""
    import OpenEXR
    a = np.ascontiguousarray(arr.astype(np.float32))
    try:
        header = {"compression": OpenEXR.ZIP_COMPRESSION, "type": OpenEXR.scanlineimage}
        OpenEXR.File(header, {"R": a, "G": a, "B": a}).write(path)
    except (AttributeError, TypeError):
        import Imath
        h = OpenEXR.Header(a.shape[1], a.shape[0])
        h["channels"] = {c: Imath.Channel(Imath.PixelType(Imath.PixelType.FLOAT)) for c in "RGB"}
        out = OpenEXR.OutputFile(path, h)
        out.writePixels({c: a.tobytes() for c in "RGB"}); out.close()


def _variants(img):
    yield "as is", img
    yield "flip rows", img[::-1]
    yield "flip columns", img[:, ::-1]
    yield "flip both", img[::-1, ::-1]
    if img.shape[0] == img.shape[1]:
        yield "transposed", img.T
        yield "transposed + flip rows", img.T[::-1]


def fit(render, target, mask):
    r, m = render[mask], target[mask]
    k = float((r * m).sum() / ((r * r).sum() + 1e-30))
    dev = k * render - target
    peak = float(target.max())
    return dict(scale=k, max_rel_dev_of_peak=float(np.abs(dev[mask]).max() / peak), rms_rel_dev_of_peak=float(np.sqrt((dev[mask] ** 2).mean()) / peak),
                median_rel_err_bright=float(np.median(np.abs(dev[mask & (target > 0.1 * peak)]) / target[mask & (target > 0.1 * peak)])) if (mask & (target > 0.1 * peak)).any() else None,
                peak=peak), dev


def gate(render_path, key, vdb_dir="results/houdini/vdb", sweep_yaml="sweeps/v1.yaml", out_dir="results/houdini", tol=0.01, extra=None):
    import yaml
    cfg = yaml.safe_load(open(sweep_yaml))
    yb = (cfg.get("beams") or {}).get(key)
    cube = load_cube(cfg["cubes"][key], name=key, beam_fwhm_px=float(yb) if yb else None)
    target = np.load(os.path.join(vdb_dir, key + "_target.npy")).astype(np.float64)
    meta = json.load(open(os.path.join(vdb_dir, key + ".json")))
    m0 = moment0(cube)
    mask = sky_mask(m0, cube.sigma_m0, 3.0, cube.valid)
    raw = read_render(render_path)
    best = None
    for how, img in _variants(raw):
        if img.shape != target.shape:
            continue
        res, dev = fit(img, target, mask)
        if best is None or res["max_rel_dev_of_peak"] < best[1]["max_rel_dev_of_peak"]:
            best = (how, res, dev, img)
    if best is None:
        raise SystemExit("render is %s, target is %s. render at 1 px per voxel (%d x %d) so nothing has to be resampled" % (raw.shape, target.shape, target.shape[1], target.shape[0]))
    how, res, dev, img = best
    passed = res["max_rel_dev_of_peak"] < tol
    out = dict(cube=key, render=os.path.abspath(render_path), orientation=how, passed=bool(passed), tolerance_of_peak=tol, **res,
               clip_cost_of_peak=meta.get("clip_cost_of_peak"), target="sum over z of the clipped density * dv", mask_pixels=int(mask.sum()),
               extra=extra or {})
    os.makedirs(out_dir, exist_ok=True)
    json.dump(out, open(os.path.join(out_dir, "gate_%s.json" % key), "w"), indent=1)
    # the picture: render, target, deviation
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 3, figsize=(10, 3.4))
    ax[0].imshow(res["scale"] * img, origin="lower", cmap="gray", vmin=0, vmax=res["peak"]); ax[0].set_title("render x %.3g" % res["scale"], fontsize=9)
    ax[1].imshow(target, origin="lower", cmap="gray", vmin=0, vmax=res["peak"]); ax[1].set_title("target (clipped sum x dv)", fontsize=9)
    lim = max(res["max_rel_dev_of_peak"], 1e-6) * res["peak"]
    im = ax[2].imshow(dev, origin="lower", cmap="RdBu_r", vmin=-lim, vmax=lim); ax[2].set_title("deviation, max %.2f%% of peak, %s" % (100 * res["max_rel_dev_of_peak"], "PASS" if passed else "FAIL"), fontsize=9)
    plt.colorbar(im, ax=ax[2], fraction=0.046)
    for a in ax:
        a.axis("off")
    fig.suptitle("%s zero point gate, orientation: %s" % (key, how), fontsize=9)
    fig.tight_layout(); fig.savefig(os.path.join(out_dir, "gate_%s.png" % key), dpi=150); plt.close(fig)
    print("%s: %s  max dev %.3f%% of peak (tol %.1f%%), rms %.3f%%, scale %.4g, orientation %s, clip cost %.2f%%" % (
        key, "PASS" if passed else "FAIL", 100 * res["max_rel_dev_of_peak"], 100 * tol, 100 * res["rms_rel_dev_of_peak"], res["scale"], how, 100 * (meta.get("clip_cost_of_peak") or 0)))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="zero point gate for a production render")
    ap.add_argument("--render", required=True, help="exr / npy / png of the plain render")
    ap.add_argument("--cube", required=True)
    ap.add_argument("--vdb-dir", default="results/houdini/vdb")
    ap.add_argument("--out", default="results/houdini")
    ap.add_argument("--tol", type=float, default=0.01, help="pass threshold, fraction of the target peak")
    ap.add_argument("--samples", type=int, default=None, help="recorded in the json: karma pixel samples used")
    ap.add_argument("--step", type=float, default=None, help="recorded in the json: volume step size / rate used")
    ap.add_argument("--note", default=None)
    a = ap.parse_args(argv)
    gate(a.render, a.cube, a.vdb_dir, out_dir=a.out, tol=a.tol, extra=dict(samples=a.samples, step=a.step, note=a.note))


if __name__ == "__main__":
    main()
