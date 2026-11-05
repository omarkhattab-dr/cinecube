# one command remakes everything. run from repo root with the venv on
PY ?= python3

.PHONY: test smoke disk sweep index figures all clean

test:            ## equivalence test + the rest
	$(PY) -m pytest -q tests

smoke:           ## 1 frame per operator on the 3 real cubes, ~1 min
	$(PY) -m cinecube.sweep sweeps/smoke.yaml

disk:            ## build the fake keplerian disk + truth
	$(PY) -m cinecube.synth --out data/synthetic_disk --inc 45

sweep: disk      ## full v1 sweep on all 4 cubes, ~5 min
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
# overleaf project 6aebf9efb11a4b10b0a24b54 is a mirror of paper/. github is the source.
# (git push of the figures 500s on overleafs side sometimes, if so upload the pngs by hand)
# .overleaf/ is a clone of the overleaf project (git ignored). first time it asks for the
# overleaf git token (overleaf -> account settings -> git integration -> generate token),
# username is already in the url (git), it only asks for the password = the token. keychain remembers it
# make overleaf       copy paper/ -> overleaf and push
# make overleaf-pull  copy overleaf edits -> paper/ (then git commit here)
OVERLEAF_URL = https://git@git.overleaf.com/6aebf9efb11a4b10b0a24b54
.PHONY: overleaf overleaf-pull overleaf-check
.overleaf:
	git clone $(OVERLEAF_URL) .overleaf

overleaf-check: .overleaf
	@cd .overleaf && [ "$$(git remote get-url origin)" = "$(OVERLEAF_URL)" ] || (echo ".overleaf is a clone of an old project, do: rm -rf .overleaf  then rerun" && exit 1)

overleaf: overleaf-check   ## push paper/ to overleaf
	cd .overleaf && git pull -q
	rsync -a --delete --exclude .git --exclude '*.aux' --exclude '*.log' --exclude '*.bbl' --exclude '*.blg' --exclude '*.out' --exclude '*.pdf' --exclude '*.synctex.gz' paper/ .overleaf/
	cd .overleaf && git add -A && (git diff --cached --quiet || git commit -q -m "sync from repo") && git push

overleaf-pull: overleaf-check   ## bring overleaf edits back into paper/
	cd .overleaf && git pull -q
	rsync -a --exclude .git .overleaf/ paper/
	@echo "now: git status, then git commit the paper changes"
