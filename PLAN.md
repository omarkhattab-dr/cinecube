# cinecube plan v2 (nov 4) - to dec 4

project: how much science survives the shot? a fidelity instrument for cinematic renders of astro
data cubes, from the proof renderer to blender. VIZA 701 fall 2026, dr kumar. omar + arash.
full version with the timeline is in the claude doc, this is the short one for the repo.

## what changed nov 4

v1 kept blender in future work and used 1 real cube. not enough, the visuals have to be the real
cinematic thing, on several objects, and the numbers stay. so:
- 2 tracks, 1 reader. track A = python (exact, the proof, cheap numbers). track B = openvdb -> blender
  cycles (the real production knobs). both scored by the same decoder + metrics.
- 4 objects not 1: l1448 (filament), fake keplerian disk (truth known), an exoALMA 12CO disk, a
  THINGS HI galaxy (or 2nd COMPLETE cloud if THINGS is down). crop to <= 256x256x128.

## the 4 things nobody does

1. **fidelity pass** - render a science pass (emission only, ortho, linear = moment0) next to the
   beauty pass in the same blender scene, reader compares them per pixel -> fidelity heat map that
   ships with the shot like a depth pass. per frame curve under an animation.
2. **fidelity envelope** - the bands become a budget (stay conditional). for every knob, both
   renderers, the largest setting still inside the band. hero shot per object = all knobs at their
   envelope values, with its scorecard.
3. **honest orbit** - on the fake disk the velocity-as-depth index gives a safe camera envelope.
   camera rig that stays in it + a disclosure shot: flat map lifts into 3d while a fidelity gauge
   drops. closer of the dec 4 talk.
4. **cross object atlas** - same 16 operators on 4 objects, rank corr between the 4 ladders. is the
   ranking universal or does absorption hurt a filament more than a disk.

1 + 2 need blender, 3 + 4 only python (fallback if blender slips).

## track A (python) - left to do

- io.py: freq axis -> km/s, BUNIT, BMAJ from header, edge channel noise. equivalence test on all 4 cubes
- sweeps/v1.yaml gets the 2 new cubes + beams, make sweep -> 4 scorecards
- envelope.py (new): per operator per object the biggest param value still >= conditional
- figures.py: atlas (4 ladders + 4x4 spearman matrix)
- index.py: safe envelope angle per stretch + camera path sampler
- sweep.frame_from_png(): score any png + legend + scale with the same code (blender bridge)

## track B (openvdb -> blender) - cinecube/blender/

1. export_vdb.py: T clipped at 0 as float grid "density" (K), voxel 1,1,stretch, dv + hash + scale in
   metadata and a json. writer = openvdb from conda-forge on the mac. fallback: export in the
   container, drop the .vdb on the mac (2 to 30 MB each)
2. scene.py (runs inside blender -b -P): import vdb, principled volume emission ~ density, absorption
   0 scatter 0, ortho cam down v, world black, view transform Standard look None exposure 0 gamma 1,
   32 bit exr, no denoise, fixed samples + step size. scene always built from a json spec
3. THE GATE: plain blender render vs moment0. pass = 1 fitted scale factor + max rel dev < 1% in the
   mask. nothing in track B counts before this passes. 2 days max (nov 10), then fallback
4. knobs (4-6 values each, every object): absorption, scatter + anisotropy, lights, color ramp,
   view transform (AgX / filmic / standard looks), dof, glare, grain, exposure, orbit + v stretch
5. score.py: every render = beauty exr + 8 bit png + science pass + json. frame_from_png scores the
   png. no legend frames (lit, scattered) use the gray legend of the science pass, paper says so
6. fidelity pass compositor template + per frame scores on a 240 frame turntable + hero frame per
   object at envelope values, 1920x1080 256 samples
7. disclosure shot on the fake disk, 10 s, plain map -> 30 deg orbit 2x stretch, index as a gauge

budget: sweeps 512px 64 samples. 10 knobs x 5 values x 4 objects = 200 frames = 1 evening.
heroes + 2 animations = 1 more evening.

## who

| | omar | arash |
| --- | --- | --- |
| code | vdb export, scene builder, gate, blender sweep, fidelity pass, heroes, disclosure, envelope.py | io.py hardening, 4 object sweep, atlas, honest orbit sampler, gallery |
| paper | abstract, method (blender half), results, discussion, future work | intro, related, method (python half), conclusion |
| talks | nov 13 blender gate + first blender scores, dec 4 closer | nov 13 gallery + atlas, nov 20 envelope + orbit, dec 4 opener |

## weeks

| when | deliverable | gate |
| --- | --- | --- |
| nov 5-8 | 4 cubes load + pass equivalence, vdb of l1448 opens in blender, gate number in results/blender/gate_l1448.json | fri sync |
| nov 9-13 | scorecard v1 on 4 objects, atlas, blender knob sweep on l1448, twin figure | progress pres 1, nov 13 |
| nov 16-20 | envelope tables, honest orbit, blender on all objects, fidelity pass, hero shots, method + related drafted | progress pres 2, nov 20 |
| nov 23-25 | disclosure shot, freeze (git tag v1.0-results, copy results/v1 + results/blender -> results/frozen) | wed nov 25 |
| nov 26 - dec 3 | results + discussion from frozen json, swap sections dec 1, deck dec 2, fresh clone make all + pdflatex from zero dec 3 | dec 4 |

nov 26 is the holiday, ask kumar if the 3rd progress slot moves.

## fallbacks

- blender gate fails (> 1% after nov 10): blender stays a scored black box, the residual is a result
  by itself, envelope from python only
- vdb export wont install: export in the container, copy the files. houdini via viz lab 2nd
- cubes too big / unreachable: crop + 2x downsample, galaxy -> 2nd COMPLETE cloud
- blender too slow: 256 px 32 samples for sweeps, drop scatter
- blender overruns: nov 13 shows the gate only, track A carries both pres, blender enters nov 20
- envelope undefined: say so (always distorting or never costs), widen grid once
- index argues with itself: keep 1-ssim only
- bands weird on a new object: raw scores + controls as lines, never retune the reader per object
- anything past nov 25 doesnt go in the paper
