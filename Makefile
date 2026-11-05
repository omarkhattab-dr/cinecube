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

# ---- overleaf (git bridge, tamu account has it)
# overleaf project "Cinematic astro cubes" is a mirror of paper/. github is the source.
# .overleaf/ is a clone of the overleaf project (git ignored). first time it asks for the
# overleaf git token (overleaf -> account settings -> git integration -> generate token),
# user = git, password = the token. mac keychain remembers it after that.
# make overleaf       copy paper/ -> overleaf and push
# make overleaf-pull  copy overleaf edits -> paper/ (then git commit here)
OVERLEAF_URL = https://git.overleaf.com/6aebf0e9a3ce890e58d38c1b
.PHONY: overleaf overleaf-pull
.overleaf:
	git clone $(OVERLEAF_URL) .overleaf

overleaf: .overleaf   ## push paper/ to overleaf
	cd .overleaf && git pull -q
	rsync -a --delete --exclude .git --exclude '*.aux' --exclude '*.log' --exclude '*.bbl' --exclude '*.blg' --exclude '*.out' --exclude '*.pdf' --exclude '*.synctex.gz' paper/ .overleaf/
	cd .overleaf && git add -A && (git diff --cached --quiet || git commit -q -m "sync from repo") && git push

overleaf-pull: .overleaf   ## bring overleaf edits back into paper/
	cd .overleaf && git pull -q
	rsync -a --exclude .git .overleaf/ paper/
	@echo "now: git status, then git commit the paper changes"
