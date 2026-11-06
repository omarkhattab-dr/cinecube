"""
exr_to_png.py - the display step for a houdini render, done here so its the same as track A

karma writes scene linear exr. the viewer sees an 8 bit png. the bridge needs to know exactly how
one became the other, so the conversion is this script, not houdinis view transform:
    display = clip(exr / scale, 0, 1)      scale = the 99.8 pct of the SCIENCE pass (plain render of the
                                           same object), so the plain render maps to the same display as
                                           track As reference
    png = colormap(display)                gray by default, any matplotlib cmap

    python -m cinecube.houdini.exr_to_png --exr renders/l1448_absorb_0p5.exr --science renders/l1448_plain.exr --cmap gray
    -> renders/l1448_absorb_0p5.png + .json (scale, cmap, science pass) ready for the bridge:
    python -m cinecube.sweep --png renders/l1448_absorb_0p5.png --cube l1448 --cmap gray --scale <display_scale_K_kms from the vdb json>

why the science pass and not the frame itself: a frame that absorbs or vignettes has a lower 99.8 pct,
normalizing it to itself would hide the loss. same rule as track A (norm_disp on the reference).
for the "view transform" knob (B4) karma can also write the png through OCIO, then this script is
skipped and the json says so. the row is flipped so y is up, like save_png in sweep.py.
"""
import argparse
import json
import os

import numpy as np
from PIL import Image

from .gate import read_render
from ..operators import colormap


def exr_to_png(exr, science, cmap="gray", out=None, flip_rows=True):
    img = read_render(exr)
    sci = read_render(science) if science and science != exr else img
    if flip_rows:                                      # exr row 0 is the top, our maps have row 0 at the bottom
        img, sci = img[::-1], sci[::-1]
    scale = float(np.percentile(sci, 99.8)) + 1e-12
    disp = np.clip(img / scale, 0, 1)
    rgb = colormap(disp, cmap)
    out = out or exr.replace(".exr", ".png")
    Image.fromarray(np.round(np.clip(rgb, 0, 1) * 255).astype(np.uint8)[::-1]).save(out)
    info = dict(exr=os.path.abspath(exr), science=os.path.abspath(science) if science else None, scale_in_exr_units=scale, cmap=cmap,
                display="clip(exr / scale, 0, 1) then colormap", shape=list(img.shape))
    json.dump(info, open(out.replace(".png", "_display.json"), "w"), indent=1)
    print("wrote %s (scale %.4g exr units at display 1.0, cmap %s)" % (out, scale, cmap))
    return out, info


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--exr", required=True)
    ap.add_argument("--science", default=None, help="the plain render of the same object, sets the display scale. default: the exr itself")
    ap.add_argument("--cmap", default="gray")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    exr_to_png(a.exr, a.science, a.cmap, a.out)


if __name__ == "__main__":
    main()
