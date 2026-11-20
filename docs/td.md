# track B in touchdesigner (nov 20)

houdini apprentice burns a "Houdini" logo into every karma render (checked on l1448_plain: full white letters in the
bottom right), so the gate can never pass there. track B moved to touchdesigner (2025.33230, non-commercial: 1280 px
cap, fine for 105-384 px cubes). the houdini scripts stay for a licensed seat.

## how to run

    make td-specs                       # vdb export + results/td/specs.json (376 frames) + colormap tables
    # touchdesigner python (textport or the mcp):
    CINECUBE_REPO = "/path/to/cinecube"
    exec(open(CINECUBE_REPO + "/cinecube/td/td_scene.py").read()); build(); run_specs()     # ~2 s, 376 frames
    make td-score                       # results/td/<cube>/scorecard.json, frames/*.png + json (track a's row shape)
    make td-twins                       # paper/figures/fig_twins_<cube>.png + results/td/twins.json
    python -m cinecube.houdini.gate --render results/td/<cube>/raw/000_reference.npy --cube <cube> --out results/td

`cinecube/td/cinecube_td.tox` is the saved network (drop it into any td project; `build()` recreates it anyway).

## renderer

- `raymarch.glsl`: the cube as a float32 3d texture (script top, `copyNumpyArray(is3D=True)`), ortho camera,
  1 px per voxel, channel 0 first along the ray (same front-to-back order as track a). output r = K km/s.
  knobs: orbit theta + velocity stretch, step, trilinear / nearest, absorption (track a's kappa = tau / (max T dv)),
  max projection, log / asinh / threshold transfer, thin-lens dof (gaussian aperture, 64 rays, blur std = sigma px
  at the front / back face, focus at the volume center), a directional light with self shadowing (single scatter,
  shadow tau 1 per peak voxel, light from up + toward the camera).
- post chain (td tops on the plain display image, clip(K / plain 99.8 pct)): lookup top colormap, bloom top
  (td's own kernel, `bloomintensity` = gain), level top gamma, teal-orange grade (glsl, track a's curve), vignette
  (glsl, track a's 1 - s r^2), noise top grain (uniform, amp = sqrt(3) sigma so the pixel std = sigma, measured).
- frames are read back as float (`numpyArray(delayed=False)`), no exr, no 8 bit step before the reader (the decoder
  quantizes like track a).

## the gate

plain frame (theta 0, step 1, trilinear at voxel centers) = sum over channels of the clipped T x dv. max deviation
0.000% of peak on all 4 cubes, scale 1, no flip (results/td/gate_<cube>.json). so the td zero point is track a's
"clip" row, not its reference: l1448 0.997, disk 0.963, j1615 0.955, ngc2403 0.898 data recovered. every td frame
carries that clip cost, same as karma would have.

## twins (td vs python, same knob, `results/td/twins.json`)

- image level, same clipped input: log, asinh, threshold, mip, absorption all 0.00% rms of peak. absorption is
  exact to 1e-6. track a's absorb lets negative noise emit, td cant, so the absorb *scores* differ (td holds up
  better on the disk and ngc2403: envelope tau 0.5 / 1.5 vs 0.35 / 0.5).
- orbit: same rotation sign, ~1.5% rms at small angles (trilinear vs ndimage.rotate). 60-90 deg differ because
  track a's rotated frame is reshaped then cropped, td keeps a fixed ortho frame.
- rank agreement over the 55 twin frames per cube: spearman 0.98 (l1448), 0.92 (disk), 0.96 (j1615), 0.87
  (ngc2403). same band on 69-89% of frames.
- where the production tools cost more than the proof version: td's bloom top (envelope gain 0.5-1 vs 1-4 on 3 of
  4 objects), td grain on the disk and ngc2403. td's light + self shadow costs less than track a's gradient shading.
- orbit envelope (1x stretch, largest angle still in the band): 2-4 deg in td, 0-4 in python. same story: the
  camera budget is a few degrees.
