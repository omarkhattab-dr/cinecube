# cinecube

how far is a cinematic render of an astro data cube from the actual data

the whole idea: linear transfer function, no absorption, camera looking straight down the velocity
axis -> the volume render IS the moment0 map. exact, not approx. so thats my zero point. every
cinematic choice after that (TF, compositing, colormap, grade, orbit, dof, lighting, bloom etc,
resampling) is an operator on top and this code scores what each one does to the data: how much
you can read back, how much structure is left, how much of the emission is still visible.

VIZA 701 fall 2026, group 5. omar + arash.

## setup (mac)

```bash
cd /Users/omarkhattab/Documents/VIZA701/cinecube
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
make test          # 12 tests, first one is the equivalence test (plain render == moment0)
```

## run

```bash
make smoke         # 1 frame per operator on l1448, few sec -> results/smoke/
make disk          # fake keplerian disk + its 3d truth -> data/synthetic_disk*
make sweep         # full v1 sweep, l1448 + disk (~40s) -> results/v1/<cube>/
make index         # velocity-as-depth index on the disk -> results/v1/index_inc45.json
make figures       # all figs into paper/figures/ from the json in results/v1/
make all           # everything
```

every frame = 1 png + 1 json (operator, params, decoder settings, scores, cube hash, version).
scorecard.json collects them + controls + bands. figures only read the json so the paper can
always be remade from scratch.

## layout

```
cinecube/        the package: io, render, operators, decode, metrics, sweep, synth, index, figures
tests/           pytest, test_equivalence.py is the one that matters
data/            l1448_13co.fits (public, 2.3mb), disk gets built by make disk
sweeps/          yaml sweeps, smoke.yaml (quick) and v1.yaml (the paper one)
docs/metrics.md  the metrics spec, code has to match this
results/         git ignored except results/frozen/ (freeze nov 25)
paper/           latex paper (same thing on overleaf), paper/figures filled by make figures
PLAN.md          scope, who does what, weeks, fallbacks
```

## how a score happens

1. `io.load_cube` reads the fits with spectral-cube. moment0 also from spectral-cube so the reference
   doesnt depend on my renderer
2. `render.render` ray marches the cube, with defaults it equals moment0
3. `operators.apply_operator` renders 1 operator (volume ops change the render call, image ops change
   the frame after the colormap)
4. `decode.decode_frame` gets data values back from the frame: 8bit quantize, display noise, nearest
   colormap color in CIELAB (bujack 2026 recipe), then display scale back to K km/s
5. `metrics.score_frame` -> data recovered (spearman over the sky mask), structure kept (ssim), flux
   visible. `metrics.controls` scores the reference frames that give the bands

## data

L1448 13CO 1-0, FCRAO COMPLETE survey, from the astropy-data repo (github.com/astropy/astropy-data).
105x105 px, 53 channels, 0.066 km/s per channel.


