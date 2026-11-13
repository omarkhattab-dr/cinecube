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
    if flip_rows:
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
