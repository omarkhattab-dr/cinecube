# cinecube plan v2 (nov 4) - to dec 4

project: how much science survives the shot? a fidelity instrument for cinematic renders of astro
data cubes, from the proof renderer to houdini. VIZA 701 fall 2026, dr kumar. omar + arash.
full version with the timeline is in the claude doc, this is the short one for the repo.
2 tracks, 1 reader. track A = python (exact, the proof, cheap numbers). track B = openvdb -> houdini (karma)
cycles (real production knobs). same decoder + metrics score both. 4 objects: l1448, fake disk,
exoALMA 12CO 3-2 disk (J1615, in repo), THINGS HI galaxy (NGC 2403, in repo) (2nd COMPLETE cloud if THINGS is down).

## the 4 things nobody does

1. **fidelity pass** - science pass (emission only, ortho, linear = moment0) rendered next to the beauty
   pass in the same houdini scene, reader compares per pixel -> fidelity heat map that ships with the
   shot like a depth pass
2. **fidelity envelope** - bands = a budget (stay conditional). per knob, both renderers, the biggest
   setting still in the band. hero shot per object = all knobs at envelope values + scorecard
3. **honest orbit** - safe camera envelope from the velocity-as-depth index on the fake disk, a rig
   that stays in it, + a disclosure shot (map lifts into 3d, fidelity gauge drops). dec 4 closer
4. **cross object atlas** - same 16 operators on 4 objects, rank corr between the ladders. universal
   or object dependent

## track A (python), in order. done = 4 scorecards + envelope + atlas + orbit + everything from make all

- [x] A0 metrics v1 (nov 4, 5c2f2b5). reader never changes after this, weird objects go in discussion
- [x] A1 exoALMA disk (nov 4): J1615-3255 12CO 3-2 (exoALMA is band 7, no 2-1. every cube in the
      release is 1.26 GB so < 500 MB wasnt an option, downloaded 1 and cropped). cinecube.prep crops
      the middle 256x256x128, Jy/beam->K, FREQ->km/s radio, beam 6 px from the header, prep json +
      HISTORY say what it did. data/exoalma_j1615_12co.fits 34 MB. equivalence + test_io pass, smoke
      controls ceiling 0.970 > beam 0.926 > shuffled 0. note in docs/metrics.md about the dynamic range
- [x] A2 THINGS galaxy (nov 4): NGC 2403 natural weighted (1.04 GB, things moved to things.www3.mpia.de,
      the old url redirects). FELO-HEL optical velocity axis + stokes axis + beam in the AIPS HISTORY,
      spectral-cube reads all 3. 4x block mean to 4 arcsec px and 384x384 (not 256: the galaxy is 22
      arcmin, 256 cut it and 6x would put the 8.75 arcsec beam under 2 px). 61 channels, Jy/beam->K.
      data/things_ngc2403_hi.fits 36 MB. tests pass (30), smoke controls ceiling 0.995 > beam 0.807 >
      shuffled 0.002. the beam blur costs a lot here because the unmasked moment0 is noisy (116 K km/s
      vs 3100 peak), so the conditional band is loose on this object. in docs/metrics.md
- [x] A3 io.py hardening (nov 4): FREQ (radio, RESTFRQ) / VRAD / FELO-VELO axes, K or Jy/beam, 4d stokes
      cubes, beam from BMAJ or the AIPS HISTORY line, yaml beam wins over the header, NaN padding (0 for
      the render, out of the mask + noise), noise_edge_channels in the yaml. test_equivalence over every
      real fits in data/, test_io.py = 1 fake fits per case checked against astropy by hand (6 tests).
      35 tests. make test from a fresh clone passes
- [x] A4 sweep (nov 4): v1.yaml 4 cubes, same grids, make sweep -> 4 scorecards in 4m54 (11 + 17 + 108 +
      155 s). controls ordered on all 4, no broken bands. 4 object controls + bands table in
      docs/metrics.md (results note). make figures draws 4 ladders, 4 galleries, 4 family plots
- [x] A5 envelope (nov 5): envelope.py + make envelope + fig_envelope.png + 2 tests. first crossing
      along the grid, none / top / value, categorical ops list whats inside, 2 param ops get 1 line per
      fixed value. grids widened once (orbit fine near 0, dof/bloom/vignette/grade/grain/bin/resample
      further out), 97 frames per cube, sweep 7 min. rules in docs/metrics.md: camera 0-4 deg is the
      whole budget, absorption tau 0.25 (l1448) to 0.5 (ngc2403), post effects nearly free except on
      l1448, spectral bin always free
- [x] A6 atlas (nov 5): fig_gallery_atlas.png, fig_atlas.png, results/v1/atlas.json. mean pairwise
      spearman 0.60, 3 objects agree (0.79-0.90), j1615 doesnt (0.24-0.47). same band everywhere:
      threshold, mip, colormap, orbit, dof, shading. 10 ops flip. note in docs/metrics.md
- [x] A7 honest orbit (nov 5): index.py fine grid + 2 thresholds (the plans band rule = 0.628 makes
      every angle safe, kept in the json, not used; headline = 2x beam on the true picture in the
      indexs own units = 0.009) + safe_angle() + safe_path(). inclinations 30/45/60 via make disk +
      make index. safe angle 2.4-3.3 deg at 1x, halves per stretch step, same answer as A5. 240 frame
      path json, max index on it = threshold. fig_index.png with the envelope + zoom inset
- [x] A8 bridge (nov 5): sweep.frame_from_png() + cli `python -m cinecube.sweep --png x.png --cube l1448
      --cmap gray --scale S --label ..` -> results/houdini/<obj>/frames/<label>.png + .json, same row
      shape, bands from results/v1/<obj>/controls.json, resizes if the png isnt the cubes size (recorded).
      round trip test to 1e-3 (found that save_png floored while the decoder rounds, fixed). 41 tests
- [ ] A9 freeze: fresh clone make all from zero (time it, README), results/v1 -> results/frozen,
      git tag v1.0-results, paper/numbers.md with the json path next to every number

## track B (openvdb -> houdini + karma), in order. starts after A3, needs A8 before B5. cinecube/houdini/

decided nov 5: houdini + karma, not blender (arash runs it, the viz lab has it, karma does volumes
better). blender stays the fallback in the risks table. everything for arash is in
cinecube/houdini/README.md: setup, commands, the gate scene node by node, what to send back.

- [x] B1 export (nov 5, python side): cinecube/houdini/export_vdb.py, make vdb -> npz + json + target
      per object + disk_truth. vdb written directly if the openvdb bindings exist, otherwise
      npz_to_vdb.py in hython does it with houdinis own tools (no bindings needed). first track B
      number: clipping negative noise costs 2% of the peak on l1448, 28% on the disk and ngc2403.
      added "clip" as a python operator so the atlas shows it. ARASH: run npz_to_vdb.py, check the
      shapes in the viewport (README section 1) -> B1 done
- [ ] B1 houdini side (arash): hython npz_to_vdb.py on the 5 npz, File sop, shapes right, name = density
- [ ] B2 scene.py (hython scene.py spec.json): file sop -> vdb, xform for the stretch, pyro shader
      emission = density + absorb 0 scatter 0, ortho cam down -z 1 px per voxel, no lights, karma rop
      cpu, linear exr, no denoise, samples + volume step from the spec, saves the hip. WRITTEN, untested
      (no houdini here), parm names self report on first run. specs/plain_<cube>.json x4 ready.
      exr_to_png.py = the display step (exr / 99.8 pct of the plain render, colormap), python side, tested
- [ ] B3 THE GATE: gate.py WRITTEN + tested here on a fake render (passes on the target x k, fails on a
      blurred one, finds the exr row flip). target = clipped sum x dv, not the raw moment0 (karma cant
      emit negatives, the clip cost is reported next to it). arash: render plain_l1448, run the gate,
      halve volume_step / double samples until it stops moving, then the other 3. 2 days max, fail ->
      houdini = scored black box, residual is a result, envelope from python only
- [ ] B4 knob sweep (sweeps/houdini_v1.yaml -> sweep_specs.py -> 1 spec per frame): absorption,
      scatter + anisotropy, lights, color ramp, view transform (OCIO looks), dof, glare, grain,
      exposure, orbit + v stretch. 4-6 values each, every object. 1 px per voxel, 64 samples,
      200 frames. save exr + spec per frame, exr_to_png makes the pngs
- [ ] B5 score.py: every png through frame_from_png (the bridge, A8 done), legendless frames (lit,
      scattered, OCIO looks) read with the gray legend of the science pass (paper says so), orbit
      frames scored twice like track A, results/houdini/<obj>/scorecard.json same shape so
      figures.py just works, fig_twins_<obj>.png (houdini curve over python curve per knob)
- [ ] B6 fidelity pass + heroes: fidelity map exr per frame (abs err decoded beauty vs science
      pass / display scale), compositor overlay template with toggle + legend, envelope_to_spec.py
      (A5 values -> houdini units), hero frame per object 1920x1080 256 samples with + without
      overlay, 240 frame l1448 turntable scored per frame
- [ ] B7 disclosure shot: fake disk, 10 s, plain map -> 30 deg orbit 2x stretch along the A7 safe
      path, index as a gauge. 2nd version that leaves the envelope on purpose. 5 frame strip in
      fig_index.png
- [ ] B8 freeze: results/houdini -> results/frozen/houdini, media -> results/frozen/media (git
      ignored, archived), numbers into paper/numbers.md

## pace (targets not a people split)

| when | what |
| --- | --- |
| nov 5-8 | A1 A2 A3, B1 B2, B3 started |
| nov 9-13 | A4 A5 A6, B3 done, B4 on l1448, B5 -> progress pres 1 nov 13 |
| nov 16-20 | A7 A8, B4 all objects, B6 -> progress pres 2 nov 20 |
| nov 23-25 | B7, A9 + B8 freeze wed nov 25 (git tag v1.0-results) |
| nov 26 - dec 3 | paper from frozen json, swap sections dec 1, deck dec 2, fresh clone check dec 3 |
| dec 4 | submit + present |

nov 26 is the holiday, ask kumar if the 3rd progress slot moves.

## fallbacks

- houdini gate fails (> 1% after nov 10): houdini stays a scored black box, residual is a result,
  envelope from python only
- no openvdb bindings: not needed, npz_to_vdb.py in hython. blender is the fallback renderer if
  houdini licensing or karma volumes turn into a time sink
- cubes too big / unreachable: crop + 2x downsample, galaxy -> 2nd COMPLETE cloud
- karma too slow: 32 samples for sweeps, xpu, drop scatter
- houdini overruns: nov 13 shows the gate only, track A carries both pres, houdini enters nov 20
- envelope undefined: say so (always distorting or never costs), widen grid once
- index argues with itself: keep 1-ssim only
- bands weird on a new object: raw scores + controls as lines, never retune the reader per object
- anything past nov 25 doesnt go in the paper
