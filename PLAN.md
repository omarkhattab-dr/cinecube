# cinecube plan to dec 4

project: how much science survives the shot? measuring cinematic rendering choices against astro
data cubes. VIZA 701 fall 2026, dr kumar. omar + arash.

## whats in the paper

- the zero point: plain render == moment0 map (done, tested)
- locked decoder + 3 scores with controls that give the bands (week 1)
- scorecard v1: 16 operators swept over their params on l1448 and the fake disk, + fair orbit
  comparison (week 2)
- velocity-as-depth index on the disk and the safe envelope from it (week 3)
- 6-8 page paper, every figure remade from the frozen results folder (week 4, dec 4)

NOT in (goes in future work): audience study, AI pipeline, blender carrier

## who does what

| | omar | arash |
| --- | --- | --- |
| code | decoder, metrics, controls, scorecard runs, index, results + discussion | fake disk, param sweeps, figure gallery, dec 4 deck |
| paper | abstract, results, discussion, future work | intro, related work, method, conclusion |

both write. swap sections dec 1 and edit each others text

## rhythm

- monday 30 min: what ships by friday, 1 github issue per task with owner + date
- friday: deliverable is in the repo and in the progress pres
- every figure from make figures, every number in the paper grepped from results/frozen/
- spec before code: docs/metrics.md is the contract, code matches the page

## weeks

| week | dates | deliverable | gate |
| --- | --- | --- | --- |
| 1 | nov 2-6 | metrics v1: decoder + scores locked, controls table, disk cube with truth | friday sync |
| 2 | nov 9-13 | scorecard v1 on l1448 + disk, fair orbit table, ladder + family curves | progress pres 1, nov 13 |
| 3 | nov 16-20 | depth index figure + safe envelope, method + related work drafted | progress pres 2, nov 20 |
| 4 | nov 23 - dec 4 | results frozen nov 25 (git tag v1.0-results), paper written + checked | paper + pres, dec 4 |

week 14 (nov 27) is a holiday, ask kumar if the 3rd progress slot moves

## fallbacks

- disk generator stalls: drop the vertical thickness (flat disk, 1 gaussian line per pixel)
- index argues with itself: keep only the 1-ssim column
- bands look weird: report raw scores with the controls as reference lines, talk about bands in discussion
- sweeps too slow: 4 values per family, HPRC last resort
