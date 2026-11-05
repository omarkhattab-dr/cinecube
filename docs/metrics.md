# metrics spec v0 (lock in week 1)

this page is the contract. decode.py and metrics.py have to match it, not the other way around.
everything below is a choice, when i lock one i write why next to it.

## the reference

plain render: additive compositing, linear TF, ortho camera down the velocity axis. equals the moment0
map from spectral-cube to float precision (max diff 3e-14 on l1448, map peaks at 7.4 K km/s).
tests/test_equivalence.py checks it every run.

## sky mask

pixels where moment0 > k=3 * sigma_m0, sigma_m0 = sigma_channel * dv * sqrt(nchan).
every score computed over the mask AND over all pixels, mask one is the headline. on l1448 the mask
is 10319 of 11025 px so they barely differ, on the disk the mask matters.

## decoder

input = the frame a viewer sees, float rgb 0..1. steps:

1. display degradation, fixed seed: round to 8 bit, gaussian noise sigma 1.5/255
2. frame + colormap ramp (256 samples) -> CIELAB
3. each pixel -> nearest ramp entry in Lab (kd tree, euclidean in Lab, close enough to delta E here).
   position along the ramp (0..1) = recovered display value
4. times the display scale (99.8 pct of the rendered image) -> K km/s

2 modes. **blind**: ramp is the base colormap only, a viewer with the legend. **informed**: a pointwise
color transform (grade) is applied to the ramp before the lookup so the decoder knows the grade, upper
bound. bloom / vignette / grain are not pointwise so informed doesnt help them. the oct 27 numbers were
blind through the base ramp. open for week 1: which mode is the headline. default now: blind.

## the 3 scores

| score | def | why | also logged |
| --- | --- | --- | --- |
| data recovered | spearman between recovered map and moment0 over the mask | monotone stretches (log, asinh) keep the order and change ratios, rank isolates the order scrambling ops | pearson, rmse, both over all px too |
| structure kept | ssim between display normalized reference and display normalized recovered map, 7 px window | standard, cheap, catches blur + absorption | same at 2x downsample (viewer further away) |
| flux visible | share of the masks reference flux whose recovered display value is >= 0.02 of frame max | what gets deleted (thresholds, vignettes, dark grades) | oct 27 legacy version, 0.2 thresh both sides |

open for week 1: the 0.02 vis thresh (0.02 makes almost everything 1.00 on l1448, legacy 0.2 is closer
to what the eye calls present), and whether structure is measured on the recovered map (now) or on the
frames luminance.

## controls (the ruler next to every number)

| control | frame | role |
| --- | --- | --- |
| ceiling | reference + quantize + noise, 100 seeds | best anything can score, 5th pct |
| beam blur | reference blurred by 2x beam (beam_px=2 on l1448, no BMAJ in header) | a physically meaningful loss |
| noise only | a noise frame | rank near 0 |
| shuffled | reference with pixels permuted | ssim floor |
| random ramp | gray gamma 0.5 decoded as linear gray | what an unknown monotone legend costs |

## bands

from the controls: preserving >= ceiling 5th pct, conditional down to the beam blur control, distorting
below. on l1448 today thats preserving >= 0.999 and conditional >= 0.966, way stricter than the oct 27
guess (0.95 / 0.80). decide in week 1: keep derived bands, soften beam blur (1x beam not 2x), or just
state the bands as a convention. sweeps/*.yaml can override with
`bands: {preserving_min: 0.95, conditional_min: 0.80}`, scorecard records which one was used.

## fair orbit comparison

orbit frames scored twice: vs moment0 (science lost from viewpoint + operator, cropped to the sky
field like oct 27) and vs the camera matched reference (same angle + stretch, linear, no absorption).
2nd one isolates the operator, the diff is the cost of the viewpoint.

## reproducibility

every frame writes a json sidecar: operator, params, decoder settings, scores, cube hash, version.
scorecard.json = all of them + controls + bands. make figures reads only json.
