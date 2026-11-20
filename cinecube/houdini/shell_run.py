# run inside the houdini gui python shell (apprentice has no hython):
#   CINECUBE_REPO = "<path to the repo>"; exec(open(CINECUBE_REPO + "/cinecube/houdini/shell_run.py").read())
# then:  run("l1448")            npz -> vdb (if missing) -> plain scene -> karma render -> exr
#        run("l1448", "cinecube/houdini/specs/absorb_l1448_tau0p5.json")   any spec
import importlib
import json
import os
import sys

import hou

# repo root: set CINECUBE_REPO in the python shell before the exec (exec has no __file__)
REPO = globals().get("CINECUBE_REPO") or os.environ.get("CINECUBE_REPO") or (
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) if "__file__" in globals() else os.getcwd())
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "cinecube", "houdini"))
import npz_to_vdb as _n2v
import scene as _scene
importlib.reload(_n2v); importlib.reload(_scene)


def apprentice():
    try:
        return hou.licenseCategory() == hou.licenseCategoryType.Apprentice
    except Exception:
        return False


def run(cube="l1448", spec_path=None, render=True):
    spec_path = spec_path or "cinecube/houdini/specs/plain_%s.json" % cube
    spec = json.load(open(spec_path))
    vdb = spec["vdb"]
    if not os.path.exists(vdb):
        _n2v.npz_to_vdb(vdb.replace(".vdb", ".npz"))
    hip = spec["out"] + (".hipnc" if apprentice() else ".hip")
    args = [spec_path, "--hip", hip] + ([] if render else ["only"])
    print("houdini %s  license %s  cwd %s" % (hou.applicationVersionString(), hou.licenseCategory(), os.getcwd()))
    _scene.main(args)
    exr = os.path.abspath(spec["out"] + ".exr")
    print("exr there: %s  %s" % (os.path.exists(exr), exr))
    return exr


def dump_parms(paths=("/mat/plain", "/out/karma"), out="results/houdini/parms_dump.json"):
    d = {}
    for p in paths:
        n = hou.node(p)
        if n is None:
            continue
        d[p] = dict(type=n.type().name(), parms={q.name(): dict(label=q.description(), value=str(q.eval()),
                    menu=list(q.menuItems()) if q.parmTemplate().type() == hou.parmTemplateType.Menu else None)
                    for q in n.parms()})
    json.dump(d, open(out, "w"), indent=1)
    print("wrote %s (%s)" % (out, ", ".join("%s %d parms" % (k, len(v["parms"])) for k, v in d.items())))


print("cinecube shell ready. type: run('l1448')")
