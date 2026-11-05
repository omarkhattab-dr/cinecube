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
