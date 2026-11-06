# metrics spec v1 (locked nov 5)

this page is the contract. decode.py and metrics.py have to match it, not the other way around.
every number below is a choice and the reason is written next to it. v0 had the open questions,
this is what we picked and why.

## the reference

plain render: additive compositing, linear TF, ortho camera down the velocity axis. equals the moment0
map from spectral-cube to float precision (max diff 3e-14 on l1448, map peaks at 7.4 K km/s).
tests/test_equivalence.py checks it every run. the reference *display* is that map through the gray
colormap, normalized so the 99.8th percentile = 1 (render.norm_disp).

## sky mask

pixels where moment0 > 3 sigma_m0, with sigma_m0 = sigma_channel * dv * sqrt(nchan).
thats the standard moment0 uncertainty when you sum every channel (teague 2019, RNAAS 3, 74),
and we do sum every channel because the render does. every score is computed over the mask AND over
all pixels, both stored, mask one is the headline and the one in the paper. on l1448 the mask is 10319
of 11025 px so they barely differ, on the disk the mask matters.

## the decoder (what a viewer can read off the frame)

input = the saved 8 bit png of the frame + the colormap legend. output = a display value 0..1 per
pixel, then times the display scale (the 99.8 pct the frame was normalized with) -> K km/s.

recipe, from bujack et al 2026 (CGF, "the truth, the whole truth..."):

1. walk the colormap ramp (1024 samples) and measure its perceptual arc length in CIEDE2000 (dE2000).
   gray is 75 dE2000 long, viridis 121, inferno 152, jet 234.
2. cut the arc into bins of **2.9 dE2000** (bujacks number, about one just noticeable difference).
   so gray has 26 readable levels, viridis 42, inferno 53, jet 81. this is the whole point: a longer
   ramp carries more levels, which is the "discriminative power" idea from bujack 2018.
3. for every pixel take the bin whose center color is nearest in dE2000. the bins center position
   on the ramp (0..1) is the recovered display value.

no display noise and no random seed. v0 had 8 bit + gaussian noise sigma 1.5/255 + euclidean Lab,
which was our own invention and we could not cite a reason for the noise level. its still in the code
as recipe: legacy so old numbers can be reproduced, not used anywhere.

why dE2000 and not euclidean Lab: dE2000 is the color difference formula that was fit to what people
actually see (sharma 2005 implementation notes), euclidean Lab (dE76) overweights lightness.
the kd tree is gone, its a brute force dE2000 to every bin center, fine at these sizes (26 to 81 bins).

2 modes, both reported, blind is the headline:
- **blind**: the ramp is the base colormap only. a viewer with the legend.
- **informed**: the ramp is pushed through the frames pointwise grade before the arc length and bins
  are built, so the decoder knows the grade. upper bound. bloom / vignette / grain are not pointwise
  so informed doesnt help them.

consequence: the reference itself does not decode to 1.000 (0.998 spearman, 0.96 ssim on l1448 with
gray). thats the cost of reading 26 levels off a legend, and the ceiling control below is exactly
that number. the equivalence (render == moment0) is exact, the decoder is not, and thats fine.

## the 3 scores

| score | def | why | also logged |
| --- | --- | --- | --- |
| data recovered | spearman rank corr between the decoded map and moment0, over the mask | monotone stretches (log, asinh) keep the order and change ratios. a rank corr is invariant to any monotone map so it only drops when an operator scrambles the *order* of the data, which is the thing a viewer cant undo with a legend. same reasoning as the order property in bujack 2018 and the invariance idea in kindlmann + scheidegger 2014 | pearson, rmse, all 3 over all pixels too |
| structure kept | ssim between the display normalized reference and the display normalized decoded map, wang 2004 settings: gaussian window 11 px sigma 1.5, K1 0.01 K2 0.03 | standard, cheap, catches blur and absorption. we use the original papers window not the scikit-image 7 px box default | same thing at 2x downsample (a viewer further from the screen). wangs own rule f = round(min(h,w)/256) says no downsampling at 105 px, so the headline is at full res |
| flux visible | share of the masks reference flux (sum of moment0 over the mask) sitting in pixels whose *displayed* color is at least **2.3 dE2000** away from the colormaps zero color | what gets deleted: thresholds, vignettes, dark grades, absorption. measured on the screen color not the decoded value, so a vignette corner that went black counts as gone. against the legends zero color not against black, so jet (dark blue at zero) works. 2.3 dE is the usual JND number (mahy 1994 via bujack 2018) | the v0 version (decoded value >= 2% of max) and the oct 27 version (>= 20%) |

why not 2% of max (the v0 choice): a gray pixel at 2% of max is 0.8 dE2000 from black, under one JND,
so every frame scored 1.00. 5% of max is about 1 JND, 10% is 5.4 dE, 20% is 13 dE. the JND rule
lands near 5% for gray and adapts to the colormap.

## controls (the ruler next to every number)

all controls go through the same decoder as the frames.

| control | frame | role |
| --- | --- | --- |
| ceiling | the reference display (gray) decoded | best anything can score, the decoders own loss. deterministic now, no seeds |
| beam blur | reference blurred by a gaussian with sigma = 2 * (beam fwhm / 2.3548) | observing the same cloud with twice the beam. a loss an astronomer would accept |
| noise only | a frame of just noise | rank near 0 |
| shuffled | reference with pixels permuted | ssim floor |
| random ramp | gray with gamma 0.5 decoded as linear gray | what an unknown monotone legend costs |

beam on l1448: no BMAJ in the header. FCRAO at 110 GHz is ~46 arcsec, pixels are 23 arcsec, so
beam_fwhm_px = 2.0 (sigma 0.85 px, 2x beam = sigma 1.7 px). v0 had a bug here, it used sigma = 2 *
beam_px = 4 px, which is ~4.7 beams not 2. fixed, and the yaml key is now beam_fwhm_px so its clear.

## bands

from the controls, on data recovered:
- **preserving**: >= ceiling. no worse than what the decoder loses on the untouched map.
- **conditional**: >= beam blur (2x). no worse than observing with twice the beam.
- **distorting**: below that.

on l1448 thats preserving >= 0.998, conditional >= 0.992. strict, and thats real: spearman barely
moves under blur (blur keeps the large scale order) but absorption tau 0.5 (0.95) and a vignette (0.95)
scramble more than doubling the beam does. the same 3 bands exist for structure kept (ceiling ssim /
beam blur ssim), stored next to the data ones. sweeps/*.yaml can still override with
bands: {preserving_min: .., conditional_min: ..}, scorecard records which one was used.

## fair orbit comparison

orbit frames scored twice: vs moment0 (science lost from viewpoint + operator, cropped to the sky
field) and vs the camera matched reference (same angle + stretch, linear, no absorption).
2nd one isolates the operator, the diff is the cost of the viewpoint.

## reproducibility

every frame writes a json sidecar: operator, params, decoder settings (recipe, jnd, mode), scores,
cube hash, version. scorecard.json = all of them + controls + bands. make figures reads only json.

## refs used here

bujack 2026 (decoder recipe, 2.9 dE2000 bins), bujack 2018 (order + discriminative power), kindlmann
+ scheidegger 2014 (invariance), wang 2004 (ssim), sharma 2005 (dE2000), mahy 1994 (JND 2.3),
teague 2019 (sigma_m0). all in paper/refs.bib. the 2.3 JND number is mahy 1994, which we only know
through bujack 2018 and didnt open, so it stays out of refs.bib until someone reads it.

## known sensitivity (nov 5)

log stretch scores 0.987 on l1448, 0.003 under the conditional line. a rank corr should not move at
all under a monotone stretch, so that 0.003 is the 26 level quantization deciding which faint pixels
tie. the bands are tight enough that a 0.003 gap is "distorting", so the paper reports the number
next to the band and does not pretend the line is sharp. same reason the ladder prints 3 decimals.

## the alma disk (A1, nov 4): what the reader does on a high dynamic range object

j1615 (exoALMA 12CO 3-2, 256x256x128, beam 6 px). controls: ceiling 0.970 / 0.735 / 0.95, beam blur
0.926 / 0.689 / 0.96, shuffled 0.000. so the bands are preserving >= 0.970, conditional >= 0.926,
way looser than l1448 (0.998 / 0.990). 2 reasons, both real:
- the plain gray display with 26 readable levels cant show a disk whose center is 196 K km/s and whose
  outer parts sit at a few sigma. most mask pixels land in the bottom 2-3 bins -> rank corr 0.97 and
  5% of the real flux is under 1 JND from black in the plain display (flux 0.95 for the reference!)
- the random ramp control (gray with gamma 0.5) scores 0.992 > ceiling. a gamma spreads the faint
  disk over more bins. same for some operators (non monotone grade 0.988, absorption tau 0.35 0.970).
  so on this object "preserving" includes things that beat the plain display, which is fine by the
  definition (>= ceiling) but has to be said in the paper: the reference *display* is not the best
  display, its the honest one (linear), and the reader measures against the data not the display.
l1448 doesnt show this because its dynamic range is small (peak 7.4 K km/s, mask almost everything).
this is exactly what the atlas (A6) is for.

## the hi galaxy (A2, nov 4): the beam blur control bites hard on a noisy moment0

ngc2403 (THINGS HI, 61x384x384, beam 2.19 px). controls: ceiling 0.995 / 0.799 / 1.00, beam blur
0.807 / 0.361 / 0.99, shuffled 0.002. bands preserving >= 0.995, conditional >= 0.807. the moment0 sums
all 61 channels and the line at any pixel only lives in 5-10 of them, so sigma_m0 = 116 K km/s against a
peak of 3100 and the faint half of the mask is noise ordered. blurring to 2x the beam reorders those
pixels -> rank corr 0.81. nothing to fix, thats what "no worse than twice the beam" means on a cube like
this, but it makes the conditional band loose (log stretch 0.822 is conditional here, distorting on l1448).
3 objects, 3 different band widths: l1448 0.998/0.990, j1615 0.970/0.926, ngc2403 0.995/0.807.

## results note (A4, nov 4): controls and bands on all 4 objects, sweep v1

same grids, same reader, nothing tuned per object. make sweep, ~5 min for 4 x 65 frames.

| object | control | data recovered | structure kept | flux visible |
| --- | --- | --- | --- | --- |
| l1448 | ceiling | 0.998 | 0.960 | 1.00 |
| l1448 | beam blur | 0.990 | 0.855 | 1.00 |
| l1448 | noise only | 0.001 | 0.021 | 0.87 |
| l1448 | shuffled | 0.011 | 0.024 | 0.94 |
| l1448 | random ramp | 0.998 | 0.736 | 1.00 |
| disk | ceiling | 0.998 | 0.862 | 1.00 |
| disk | beam blur | 0.895 | 0.372 | 1.00 |
| disk | noise only | 0.015 | 0.014 | 0.87 |
| disk | shuffled | 0.011 | 0.015 | 0.51 |
| disk | random ramp | 0.996 | 0.491 | 1.00 |
| j1615 | ceiling | 0.970 | 0.735 | 0.95 |
| j1615 | beam blur | 0.926 | 0.689 | 0.96 |
| j1615 | noise only | -0.001 | 0.011 | 0.87 |
| j1615 | shuffled | 0.000 | 0.096 | 0.46 |
| j1615 | random ramp | 0.992 | 0.362 | 1.00 |
| ngc2403 | ceiling | 0.995 | 0.799 | 1.00 |
| ngc2403 | beam blur | 0.807 | 0.361 | 0.99 |
| ngc2403 | noise only | 0.002 | 0.009 | 0.86 |
| ngc2403 | shuffled | 0.002 | 0.015 | 0.52 |
| ngc2403 | random ramp | 0.996 | 0.478 | 1.00 |

bands that came out of it (data recovered / structure kept):

| object | preserving >= | conditional >= | structure preserving >= | structure conditional >= | frames preserving / conditional / distorting |
| --- | --- | --- | --- | --- | --- |
| l1448 | 0.998 | 0.990 | 0.960 | 0.855 | 9 / 15 / 41 |
| disk | 0.998 | 0.895 | 0.862 | 0.372 | 8 / 28 / 29 |
| j1615 | 0.970 | 0.926 | 0.735 | 0.689 | 13 / 19 / 33 |
| ngc2403 | 0.995 | 0.807 | 0.799 | 0.361 | 6 / 31 / 28 |

checks the plan asks for: controls are ordered (ceiling > beam blur > shuffled) on all 4, nothing is
"everything distorting", no object has the ceiling under the beam blur. so no object needs a note for
the bands being broken. things for discussion (not for retuning):
- the random ramp (gamma 0.5 gray) beats the ceiling on 3 of 4 objects. a gamma is a better *display*
  than linear gray when the dynamic range is big. the reader is honest about that, the bands are
  relative to the plain display and the paper has to say so
- noise only gets flux 0.87 everywhere: a frame of pure noise has 87% of its pixels brighter than 1 JND,
  so flux visible alone cant tell noise from data. its the 3rd score for a reason, not the 1st
- the conditional width goes from 0.008 (l1448) to 0.19 (ngc2403). twice the beam means something
  different on a clean single dish map and on a noisy 61 channel sum. same rule, 4 answers

## results note (A5, nov 5): envelopes, sweep v1 with the grids widened once

make envelope -> results/v1/envelope.json + envelope.md, fig_envelope.png. envelope = biggest grid value
still inside the band, first crossing (a dip stops it). 97 frames per cube after the widening (orbit
theta 0 2 4 6 8 10 15 20 30 45 60 90, dof to 8, bloom gain to 4, vignette to 1, grade to 1, grain
0.01-0.1, bin + resample to 8). the rules it gives, "stay conditional":

| knob | l1448 | disk | j1615 | ngc2403 |
| --- | --- | --- | --- | --- |
| absorption tau up to | 0.25 | 0.35 | 0.35 | 0.5 |
| lighting strength up to | 0.2 | 0.6 | 0.35 | 0.6 |
| orbit at 1x stretch up to | 0 deg | 2 deg | 4 deg | 4 deg |
| orbit at 2x / 3x | 0 / 0 | 0 / 0 | 2 / 0 | 2 / 0 |
| dof sigma up to | 4 | 6 | 8 (top) | 4 |
| threshold k up to | 1 | 2 | 1 | 2 |
| bloom gain up to | 1.0 | 4 (top) | 4 (top) | 4 (top) |
| vignette up to | none | 1.0 (top) | 0.5 | 1.0 (top) |
| teal orange grade up to | 1.0 (top) | 1.0 (top) | 0.2 | 1.0 (top) |
| sky resample | none | 2x | 4x | 2x |
| spectral bin | 8 (top) | 8 (top) | 8 (top) | 8 (top) |

what it says:
- the camera is the expensive knob everywhere. 0 to 4 degrees of orbit is all the budget allows on any
  object, and any velocity stretch above 1x kills it. everything the paper says about "3d" cinematic
  cubes starts from this number. A7 (honest orbit on the disk, fine grid 0-10 deg) is where it gets
  resolved properly
- absorption and lighting envelopes scale with the object: the clean single dish filament (l1448)
  tolerates least (tau 0.25, light 0.2), the noisy galaxy most (tau 0.5, light 0.6), because its band is
  the loosest. so "how much absorption is ok" has no single answer, it depends on how noisy the map
  already is. thats a real result for the atlas, not a calibration problem
- post effects (bloom, vignette, grain, grade) are nearly free on 3 of 4 objects even at the top of the
  widened grids. l1448 is the exception: vignette is always out and bloom stops at gain 1, because on
  a map where everything is signal (mask = 94% of pixels) darkening the corners deletes real flux
- spectral binning up to 8 never leaves the band anywhere. summing channels before the render is the
  same sum the moment0 does, so the reader cant see it. correct, and it means spectral_bin isnt a
  cinematic cost, its free compression
- "top of grid" survivors after one widening (bloom, vignette, grade, grain, bin): the rule says widen
  once, done. theyre reported as "never costs anything at the tested range", not widened again

## results note (A6, nov 5): the atlas, is the ranking universal

make figures -> fig_gallery_atlas.png, fig_atlas.png, results/v1/atlas.json. 16 operators at their
registry defaults (nearest swept value), ranked by data recovered on each object, spearman between
the 4 rankings:

| | disk | j1615 | l1448 | ngc2403 |
| --- | --- | --- | --- | --- |
| disk | 1 | 0.24 | 0.79 | 0.90 |
| j1615 | 0.24 | 1 | 0.36 | 0.47 |
| l1448 | 0.79 | 0.36 | 1 | 0.83 |
| ngc2403 | 0.90 | 0.47 | 0.83 | 1 |

mean of the 6 pairs: **0.60**. the sentence: the ranking is only moderately universal. 3 objects agree
(0.79 to 0.90), the alma disk j1615 doesnt (0.24 to 0.47). same band on all 4 objects: threshold, mip,
colormap, orbit, dof, shading (the camera / lighting / compositing knobs, always the same answer).
band flips between objects: log, asinh, absorb, both grades, bloom, vignette, grain, spectral_bin,
sky_resample, mostly conditional everywhere except distorting on l1448 (tightest band) or the other
way round on j1615. why j1615 is the odd one: its mask is mostly faint pixels in the bottom gray bins,
so anything that stretches the faint end (a grade, a gamma, even a non monotone grade) reads better
than the plain display, and things that are free elsewhere (teal orange grade: 0.743, last place)
cost there because the grade pushes the faint disk into teal and the gray legend cant read it.

## results note (A7, nov 5): the honest orbit

make index -> index_inc30/45/60.json + safe_path_inc45.json, fig_index.png. fine grid near 0
(0 2 4 6 8 10 15 20 30 45 60 90), 3 stretches, 3 inclinations.

the threshold: the plan said "1 minus the disks structure conditional band". thats 1 - 0.372 = 0.628
and the index never gets above 0.42, so every angle would be safe (status "all" at 90 deg on all 3
inclinations, its in the json as safe_angle.band). the reason: that band comes from the reader + 2x
beam blur on a smooth disk through 26 gray levels, a different currency from the index which has no
decoder in it. so the headline threshold is the same rule in the indexs own currency: 1 - ssim between
the true density picture and the same picture blurred to 2x the beam = 0.009-0.010. safe angle =
biggest theta with index under that, first crossing, interpolated:

| inclination | 1x stretch | 2x | 3x |
| --- | --- | --- | --- |
| 30 | 3.3 deg | 2.0 | 1.4 |
| 45 | 2.5 deg | 1.7 | 1.2 |
| 60 | 2.4 deg | 1.7 | 1.2 |

2 independent routes, same answer: the envelope (reader + spearman, A5) said 0-4 deg at 1x, the index
(no reader, ssim vs the true 3d density) says 2.4-3.3 deg. a camera orbit on a ppv cube is honest for
about 3 degrees and a velocity stretch halves that. everything past it is interpretation, which is the
point of the disclosure shot.

safe_path_inc45.json: 240 frames, 2 legs (stretch 1 out to 2.5 deg and back, stretch 2 out to 1.7 and
back, eased), index rendered per frame not interpolated, max on the path 0.0090 = the threshold, inside.
its a tiny move. thats the honest number, the disclosure shot (B7) is the one that leaves it on purpose.

## the bridge (A8, nov 5)

any png + a legend + a scale can be scored like a sweep frame: sweep.frame_from_png(). same reader,
same mask, same bands (read from results/v1/<cube>/controls.json). the scale is the K km/s at display
1.0, which for a blender beauty pass is the 99.8 pct of its science pass. one thing it found: save_png
used to floor to 8 bit while the decoder rounds, so a frame on disk could be 1 level off from the frame
that was scored. fixed (rounds now), the old pngs in results/v1 are 1 level off until the freeze
rewrites them, the json scores were always right.
