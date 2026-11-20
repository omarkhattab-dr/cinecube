PY ?= python3

.PHONY: test smoke disk sweep index envelope figures all clean vdb td-specs td-score td-twins

test:
	$(PY) -m pytest -q tests

smoke:
	$(PY) -m cinecube.sweep sweeps/smoke.yaml

disk:
	$(PY) -m cinecube.synth --out data/synthetic_disk --inc 45
	$(PY) -m cinecube.synth --out data/synthetic_disk_inc30 --inc 30
	$(PY) -m cinecube.synth --out data/synthetic_disk_inc60 --inc 60

sweep: disk
	$(PY) -m cinecube.sweep sweeps/v1.yaml

index: disk
	mkdir -p results/v1
	$(PY) -m cinecube.index --disk data/synthetic_disk.fits --truth data/synthetic_disk_truth.npz --out results/v1/index_inc45.json
	$(PY) -m cinecube.index --disk data/synthetic_disk_inc30.fits --truth data/synthetic_disk_inc30_truth.npz --out results/v1/index_inc30.json
	$(PY) -m cinecube.index --disk data/synthetic_disk_inc60.fits --truth data/synthetic_disk_inc60_truth.npz --out results/v1/index_inc60.json
	$(PY) -m cinecube.index --path results/v1/index_inc45.json --frames 240 --out results/v1/safe_path_inc45.json

vdb:
	$(PY) -m cinecube.houdini.export_vdb
	@echo "next, in houdini: hython cinecube/houdini/npz_to_vdb.py results/houdini/vdb/*.npz"

td-specs: vdb
	$(PY) -m cinecube.td.sweep_td specs sweeps/td_v1.yaml
	@echo "next, in touchdesigner python: CINECUBE_REPO = '$(CURDIR)'; exec(open(CINECUBE_REPO + '/cinecube/td/td_scene.py').read()); build(); run_specs()"

td-score:
	$(PY) -m cinecube.td.sweep_td score sweeps/td_v1.yaml

td-twins:
	$(PY) -m cinecube.td.sweep_td twins sweeps/td_v1.yaml

envelope:
	$(PY) -m cinecube.envelope results/v1

figures:
	$(PY) -m cinecube.figures results/v1 paper/figures

all: test sweep index envelope figures

clean:
	rm -rf results/smoke results/v1 paper/figures/*.png

OVERLEAF_URL = https://git@git.overleaf.com/6aebf9efb11a4b10b0a24b54
.PHONY: overleaf overleaf-pull overleaf-check
.overleaf:
	git clone $(OVERLEAF_URL) .overleaf

overleaf-check: .overleaf
	@cd .overleaf && [ "$$(git remote get-url origin)" = "$(OVERLEAF_URL)" ] || (echo ".overleaf is a clone of an old project, do: rm -rf .overleaf  then rerun" && exit 1)

overleaf: overleaf-check
	cd .overleaf && git pull -q
	rsync -a --delete --exclude .git --exclude '*.aux' --exclude '*.log' --exclude '*.bbl' --exclude '*.blg' --exclude '*.out' --exclude '*.pdf' --exclude '*.synctex.gz' paper/ .overleaf/
	cd .overleaf && git add -A && (git diff --cached --quiet || git commit -q -m "sync from repo") && git push

overleaf-pull: overleaf-check
	cd .overleaf && git pull -q
	rsync -a --exclude .git .overleaf/ paper/
	@echo "now: git status, then git commit the paper changes"
