# track B: houdini + karma

this folder is everything track B needs. the idea: the same cubes go into houdini as vdb, karma renders
them, and every render comes back through the same reader as track A (`python -m cinecube.sweep --png`).
nothing here is tuned by hand, every scene comes from a json spec so it can be rerun.

written without a houdini to test on. the python side (export, gate, exr -> png, bridge) is tested.
the 2 hython scripts (npz_to_vdb.py, scene.py) print what they do and which parm names they found, so
the first run tells us what to fix. the manual recipe below is the same scene node by node, build it by
hand if the script trips, the gate doesnt care how the render was made.

## 0. setup on the render box

```bash
git clone https://github.com/omarkhattab-dr/cinecube.git
cd cinecube
python3 -m venv .venv && source .venv/bin/activate      # python side
pip install -r requirements.txt
pip install OpenEXR                                     # for the gate (reads karma exr)
make test                                               # 42 tests, the equivalence test on 3 real cubes
make disk                                               # the fake disks
```
houdini 20.x. `hython` is in the houdini bin folder (`/opt/hfs20.5/bin/hython` on linux,
`/Applications/Houdini/Houdini20.5.xxx/Frameworks/Houdini.framework/Versions/Current/Resources/bin/hython`
on mac, `C:\Program Files\Side Effects Software\Houdini 20.5.xxx\bin\hython.exe` on windows).
no openvdb python bindings needed anywhere, houdini does the vdb part.

## 1. B1: the volumes

```bash
python -m cinecube.houdini.export_vdb                    # -> results/houdini/vdb/<key>.npz + .json + _target.npy
hython cinecube/houdini/npz_to_vdb.py results/houdini/vdb/*.npz     # -> <key>.vdb
```
5 files: l1448, disk, j1615, ngc2403 and disk_truth (the fake disks real 3d density, for B7).
the json next to each vdb has dv, the display scale (K km/s at display 1.0), the cube hash, the
clipping cost. read it once, the numbers in it show up again in the bridge.

**check (done when):** File sop -> the vdb, display it. l1448 is a 105 x 105 x 53 box with the filament
diagonal, j1615 a 256 x 256 x 128 box with a disk in the middle, ngc2403 384 x 384 x 61 with a galaxy,
disk 128 x 128 x 64 with a tilted ring. voxel size 1 x 1 x 1 (the stretch is applied in the scene, not in
the vdb). the volume should be named "density" (Geometry Spreadsheet, primitive attribute name).

geometry convention, important for every camera: voxel (x, y, z) = (ra pixel, dec pixel, channel).
the sky is the x y plane, velocity is z. the gate camera looks down -z. 1 render pixel = 1 voxel.

## 2. B2 + B3: the gate scene and the gate

```bash
hython cinecube/houdini/scene.py cinecube/houdini/specs/plain_l1448.json          # builds + renders
hython cinecube/houdini/scene.py cinecube/houdini/specs/plain_l1448.json --hip only   # just saves the hip
python -m cinecube.houdini.gate --render results/houdini/renders/l1448_plain.exr --cube l1448 --samples 64 --step 0.5
```
the gate fits 1 scale factor between the exr and the target (sum over z of the clipped density x dv),
tries the 4 flips so a mirrored camera doesnt fail for the wrong reason, and passes when the max
deviation inside the sky mask is under 1% of the target peak. it writes results/houdini/gate_l1448.json
and gate_l1448.png (render, target, deviation map). look at the deviation map: a smooth bias = step
size too big, speckle = not enough samples, a shifted edge = camera half a pixel off.

loop: halve volume_step, double samples, rerun, until the gate number stops moving. write the
settings that pass into the spec (they get copied into every later spec). 2 days max on this, if it
doesnt pass we keep houdini as a scored black box and say so in the paper (plan, risks).

then the other 3: plain_disk, plain_j1615, plain_ngc2403 (specs are there).

### the gate scene by hand (same as scene.py)

- /obj/cinecube (geo): File sop -> results/houdini/vdb/l1448.vdb. Transform sop after it with scale
  (1, 1, stretch), stretch = 1 for the gate. OUT null with display + render flags.
- /obj/cam: Projection = Orthographic. Ortho Width = nx (105 for l1448). Resolution nx x ny, pixel aspect 1.
  Translate (nx/2, ny/2, nz + 100), rotate (0, 0, 0): it looks down -z at the middle of the field.
  near 0.1, far 2 x (nz + 200). no dof.
- no lights. none. delete the default ones if a template added any.
- material on the geo: a volume shader with emission = density and nothing else:
  - Pyro Shader (karma): Smoke density scale 0 (no absorption), scattering 0, Fire / emission field =
    "density", emission intensity 1, color mode constant (not blackbody), color white. nothing else on.
  - or in a Karma Material Builder: a MaterialX standard volume with absorption 0, scattering 0,
    emission = density grid x 1, white.
  the gate fits the scale so "1" can be anything, what matters is: linear in density, no absorption,
  no scatter.
- /out karma rop: camera /obj/cam, resolution 105 x 105 (override the camera res if it asks), engine
  CPU for the gate (exact ray marching; XPU later for speed), pixel samples 64, volume step rate 0.5,
  denoiser OFF, motion blur off, output results/houdini/renders/l1448_plain.exr, 32 bit float.
- do not apply any view transform / OCIO look to the exr. karma exr is scene linear, thats what we want.
  the png the viewer sees is made by exr_to_png.py here, not by houdini (see 3).

## 3. B4 + B5: the knobs, and getting a render back through the reader

every knob is a field in a spec. copy plain_l1448.json, change one field, new "out" name:
```bash
hython cinecube/houdini/scene.py cinecube/houdini/specs/absorb_l1448_tau0p5.json
python -m cinecube.houdini.exr_to_png --exr results/houdini/renders/l1448_absorb_0p5.exr \
        --science results/houdini/renders/l1448_plain.exr --cmap gray
python -m cinecube.sweep --png results/houdini/renders/l1448_absorb_0p5.png --cube l1448 --cmap gray \
        --scale 6.258 --label "houdini absorb 0.5" --params '{"absorption": 0.5}'
```
`--scale` = display_scale_K_kms from results/houdini/vdb/l1448.json (6.258 for l1448). the display
step divides the exr by the 99.8 pct of the PLAIN render of the same object, so the plain houdini
frame maps to the same display as track As reference. the bridge writes
results/houdini/l1448/frames/<label>.png + .json.

knob list for B4 (4 to 6 values each, every object), spec field -> what it is in houdini:
| spec field | houdini | python twin |
| --- | --- | --- |
| absorption | pyro smoke density scale | absorb tau |
| scatter, anisotropy | pyro scattering, phase | none (new) |
| light | a sun / point light + its intensity | shading |
| color_ramp | emission color from a ramp over density (do in the shader, or exr_to_png --cmap) | colormap, grade |
| view_transform | karma / mplay OCIO look (AgX, filmic) written as png by houdini | grade (non pointwise) |
| dof | camera fstop + focus | dof |
| glare, grain | COP / compositing after the render | bloom, grain |
| exposure | exr_to_png scale, or karma exposure | linear scale (preserving) |
| theta_deg, stretch | camera orbit + the z scale | orbit |

a sweep = many specs. `sweep_specs.py` (not written yet, B4) will generate them from a yaml like
sweeps/v1.yaml. until then copy the json by hand, its 10 lines.

## 4. what to send back after the first gate run

- results/houdini/gate_l1448.json + gate_l1448.png
- the printout of scene.py (the "material:", "rop:" and any "NONE of these parms" lines)
- the hip file it saved, if the script got that far

## 5. files

| file | runs where | what |
| --- | --- | --- |
| export_vdb.py | python | cube -> npz + json + target (+ vdb if the bindings exist) |
| npz_to_vdb.py | hython | npz -> vdb with houdinis volume tools |
| scene.py | hython | json spec -> scene -> karma render (exr) + hip |
| gate.py | python | plain exr vs the target, pass / fail, deviation map |
| exr_to_png.py | python | linear exr -> the 8 bit png a viewer sees, documented transform |
| specs/ | json | one per render. plain_<cube> are the gate scenes |
