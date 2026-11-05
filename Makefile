# one command remakes everything. run from repo root with the venv on
PY ?= python3

.PHONY: test smoke disk sweep index figures all clean

test:            ## equivalence test + the rest
	$(PY) -m pytest -q tests

smoke:           ## 1 frame per operator on l1448, few seconds
	$(PY) -m cinecube.sweep sweeps/smoke.yaml

disk:            ## build the fake keplerian disk + truth
	$(PY) -m cinecube.synth --out data/synthetic_disk --inc 45

sweep: disk      ## full v1 sweep, l1448 + disk
	$(PY) -m cinecube.sweep sweeps/v1.yaml

index: disk      ## velocity-as-depth index on the disk
	mkdir -p results/v1
	$(PY) -m cinecube.index --disk data/synthetic_disk.fits --truth data/synthetic_disk_truth.npz --out results/v1/index_inc45.json

figures:         ## all figures into paper/figures from results/v1
	$(PY) -m cinecube.figures results/v1 paper/figures

all: test sweep index figures

clean:
	rm -rf results/smoke results/v1 paper/figures/*.png

# ---- overleaf (git bridge, the tamu account has it)
# once: blank overleaf project, Menu -> Git -> copy the clone url, then
#   git remote add overleaf https://git.overleaf.com/<project id>
# then make overleaf pushes paper/ there, make overleaf-pull brings overleaf edits back
# overleaf asks for the git token the first time (account settings -> git integration)
.PHONY: overleaf overleaf-pull
overleaf:        ## push paper/ to overleaf
	git subtree push --prefix=paper overleaf master

overleaf-pull:   ## pull overleaf edits back into paper/
	git subtree pull --prefix=paper overleaf master -m "pull from overleaf"
