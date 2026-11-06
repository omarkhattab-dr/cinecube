"""the bridge: a sweep frame saved to png and scored through frame_from_png gives the same numbers"""
import json
import os
import numpy as np
import pytest

from cinecube.io import load_cube, moment0, sky_mask
from cinecube.render import render, norm_disp
from cinecube.operators import apply_operator
from cinecube.decode import decode_frame, zero_color_lab
from cinecube.metrics import score_frame
from cinecube.sweep import save_png, frame_from_png, load_png

ROOT = os.path.join(os.path.dirname(__file__), "..")


@pytest.mark.parametrize("op,params,cmap", [("absorb", {"tau": 0.5}, "gray"), ("colormap", {"cmap": "inferno"}, "inferno")])
def test_png_round_trip_matches_in_memory(tmp_path, op, params, cmap):
    cube = load_cube(os.path.join(ROOT, "data", "l1448_13co.fits"), name="l1448", beam_fwhm_px=2.0)
    m0 = moment0(cube); ref = render(cube.T, cube.dv); ref01 = norm_disp(ref)
    mask = sky_mask(m0, cube.sigma_m0, 3.0, cube.valid)
    fr = apply_operator(cube, op, params)
    rec, _ = decode_frame(fr)
    mem = score_frame(m0, ref01, rec, mask, fr["rgb"], zero_color_lab(fr["cmap"]))["headline"]
    png = str(tmp_path / "frame.png")
    save_png(fr["rgb"], png)
    assert np.allclose(load_png(png), np.round(np.clip(fr["rgb"], 0, 1) * 255) / 255, atol=1e-9)   # the flip undoes itself
    row = frame_from_png(png, "l1448", cmap=cmap, scale=fr["scale"], params=params, label="rt_" + op,
                         sweep_yaml=os.path.join(ROOT, "sweeps", "v1.yaml"), out_root=str(tmp_path / "out"), bands_from=os.path.join(ROOT, "results", "v1"))
    for k in ("data_recovered", "structure_kept", "flux_visible"):
        assert abs(row[k] - mem[k]) < 1e-3, k
    assert os.path.exists(tmp_path / "out" / "l1448" / "frames" / ("rt_" + op + ".json"))
    saved = json.load(open(tmp_path / "out" / "l1448" / "frames" / ("rt_" + op + ".json")))
    assert saved["cube"] == "l1448" and saved["params"] == params and saved["scale"] == pytest.approx(fr["scale"])


def test_resize_when_sizes_differ(tmp_path):
    from PIL import Image
    cube = load_cube(os.path.join(ROOT, "data", "l1448_13co.fits"), name="l1448", beam_fwhm_px=2.0)
    fr = apply_operator(cube, "reference")
    png = str(tmp_path / "big.png")
    save_png(fr["rgb"], png)
    Image.open(png).resize((210, 210), Image.BILINEAR).save(png)       # pretend blender rendered at 2x
    row = frame_from_png(png, "l1448", cmap="gray", label="big", sweep_yaml=os.path.join(ROOT, "sweeps", "v1.yaml"),
                         out_root=str(tmp_path / "out"), bands_from=os.path.join(ROOT, "results", "v1"))
    assert row["resized_from"] == [210, 210]
    assert row["data_recovered"] > 0.99
