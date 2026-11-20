# builds /project1/cinecube inside touchdesigner and renders sweep frames. run in td python:
#   CINECUBE_REPO = "<path to the repo>"; exec(open(CINECUBE_REPO + "/cinecube/td/td_scene.py").read())
#   build("l1448"); render_frame("results/td/renders/l1448_plain.npy")     # gate frame
#   run_specs("results/td/specs.json")                                     # the whole sweep
# volume knobs live in raymarch.glsl (r = K km/s, saved as float .npy, python does the display like track a).
# post knobs are td's own tops on the display image (bloom, level, lookup grade, ramp vignette, noise grain,
# lookup colormap), saved as float rgb .npy, python quantizes + decodes it like any other frame.
import json
import os
import time

import numpy as np

# repo root: set CINECUBE_REPO (td python variable or env var) before the exec, else td's working folder
REPO = globals().get("CINECUBE_REPO") or os.environ.get("CINECUBE_REPO") or os.getcwd()
if not os.path.isdir(os.path.join(REPO, "cinecube", "td")):
    raise RuntimeError("set CINECUBE_REPO = '<path to the cinecube repo>' before exec(open(...).read())")
VDB = os.path.join(REPO, "results/houdini/vdb")
GLSL = os.path.join(REPO, "cinecube/td/raymarch.glsl")
DISPLAY_GLSL = """uniform vec4 uDisp;  // 1 / display scale
out vec4 fragColor;
void main() {
    float v = clamp(texture(sTD2DInputs[0], vUV.st).r * uDisp.x, 0.0, 1.0);
    fragColor = TDOutputSwizzle(vec4(v, v, v, 1.0));
}
"""
GRADE_GLSL = """uniform vec4 uGrade;  // strength
out vec4 fragColor;
// same curve as track a's teal-orange grade, written as a td grade pass: sigmoid on luminance, teal -> orange tint
void main() {
    vec3 c = texture(sTD2DInputs[0], vUV.st).rgb;
    float lum = (c.r + c.g + c.b) / 3.0;
    float lo = 1.0 / (1.0 + exp(4.0)), hi = 1.0 / (1.0 + exp(-4.0));
    float s = (1.0 / (1.0 + exp(-8.0 * (lum - 0.5))) - lo) / (hi - lo);
    vec3 tint = mix(vec3(0.0, 0.55, 0.6), vec3(1.0, 0.6, 0.2), s);
    fragColor = TDOutputSwizzle(vec4(clamp(c * (1.0 - uGrade.x) + uGrade.x * s * tint, 0.0, 1.0), 1.0));
}
"""
VIGNETTE_GLSL = """uniform vec4 uVig;  // strength
out vec4 fragColor;
// track a's vignette: 1 - strength * clip(r, 0, 1)^2, r = 1 at the middle of each edge
void main() {
    vec3 c = texture(sTD2DInputs[0], vUV.st).rgb;
    vec2 q = (vUV.st - 0.5) * 2.0;
    float r = clamp(length(q), 0.0, 1.0);
    fragColor = TDOutputSwizzle(vec4(clamp(c * (1.0 - uVig.x * r * r), 0.0, 1.0), 1.0));
}
"""
GRAIN_AMP_PER_STD = 3.0 ** 0.5   # td noise top type random is uniform in [-amp, amp]: std = amp / sqrt(3), measured 0.029 at amp 0.05
CALLBACKS = '''import numpy as np
def onSetupParameters(scriptOp):
    return
def onPulse(par):
    return
def onCook(scriptOp):
    arr = scriptOp.parent().fetch(scriptOp.name + "_arr", None)
    if arr is not None:
        scriptOp.copyNumpyArray(arr, is3D=(arr.ndim == 4))
    return
'''
F32 = "rgba32float"


def _meta(key):
    return json.load(open(os.path.join(VDB, key + ".json")))


def _get(c, typ, name, x, y):
    n = c.op(name) or c.create(typ, name)
    n.nodeX, n.nodeY = x, y
    try:
        n.par.format = F32
    except Exception:
        pass
    return n


def _uniforms(g, vals):
    for i, (name, v) in enumerate(vals):
        setattr(g.par, "vec%dname" % i, name)
        for j, comp in enumerate("xyzw"):
            setattr(g.par, "vec%dvalue%s" % (i, comp), float(v[j]))


def build(key="l1448"):
    root = op("/project1")
    c = root.op("cinecube") or root.create(baseCOMP, "cinecube")
    cb = c.op("script_callbacks") or c.create(textDAT, "script_callbacks")
    cb.text = CALLBACKS
    for old in ("cube_callbacks",):
        if c.op(old):
            c.op(old).destroy()
    s = _get(c, scriptTOP, "cube", 0, 0); s.par.callbacks = cb
    src = c.op("raymarch_glsl") or c.create(textDAT, "raymarch_glsl")
    src.par.file = GLSL; src.par.syncfile = True
    g = _get(c, glslTOP, "render", 200, 0)
    g.inputConnectors[0].connect(s)
    g.par.pixeldat = src; g.par.outputresolution = "custom"
    # display: K km/s -> 0..1 gray with the plain render's scale (track a: norm_disp of the reference)
    dsrc = c.op("display_glsl") or c.create(textDAT, "display_glsl"); dsrc.text = DISPLAY_GLSL
    d = _get(c, glslTOP, "display", 400, 0); d.inputConnectors[0].connect(g); d.par.pixeldat = dsrc
    # colormap: td lookup top against a 256 x 1 ramp texture (matplotlib values, written by the script top)
    ramp = _get(c, scriptTOP, "cmap_ramp", 400, -150); ramp.par.callbacks = cb
    lk = _get(c, lookupTOP, "colormap", 600, 0); lk.inputConnectors[0].connect(d); lk.inputConnectors[1].connect(ramp)
    bl = _get(c, bloomTOP, "bloom", 800, 0); bl.inputConnectors[0].connect(lk)
    lv = _get(c, levelTOP, "exposure", 1000, 0); lv.inputConnectors[0].connect(bl)
    gsrc = c.op("grade_glsl") or c.create(textDAT, "grade_glsl"); gsrc.text = GRADE_GLSL
    gr = _get(c, glslTOP, "grade", 1200, 0); gr.inputConnectors[0].connect(lv); gr.par.pixeldat = gsrc
    for old in ("vignette", "vignette_ramp", "vignette_keys", "vignette_ramp_keys", "cube_callbacks1"):
        o = c.op(old)
        if o is not None and (old != "vignette" or o.type != "glsl"):
            o.destroy()
    vsrc = c.op("vignette_glsl") or c.create(textDAT, "vignette_glsl"); vsrc.text = VIGNETTE_GLSL
    vg = _get(c, glslTOP, "vignette", 1400, 0); vg.inputConnectors[0].connect(gr); vg.par.pixeldat = vsrc
    nz = _get(c, noiseTOP, "grain_noise", 1400, -150)
    gn = _get(c, compositeTOP, "grain", 1600, 0); gn.inputConnectors[0].connect(vg); gn.inputConnectors[1].connect(nz)
    gn.par.operand = "add"
    out = _get(c, nullTOP, "OUT", 1800, 0); out.inputConnectors[0].connect(gn)
    load(key)
    set_post()
    return c


def load(key):
    c = op("/project1/cinecube")
    d = np.load(os.path.join(VDB, key + ".npz"), allow_pickle=False)
    # channel 0 first along the ray (camera at +z looks down -z), same front-to-back order as track a's render
    T = np.ascontiguousarray(d["density"].astype(np.float32)[::-1])
    c.store("cube_arr", np.ascontiguousarray(T.reshape(T.shape + (1,))))
    c.store("cube_key", key)
    c.store("cube_Tmax", float(T.max()))
    nz_, ny, nx = T.shape
    for n in ("render", "display", "colormap", "bloom", "exposure", "grade", "vignette", "grain_noise", "grain", "OUT"):
        o = c.op(n)
        if o is not None and hasattr(o.par, "outputresolution"):
            o.par.outputresolution = "custom"
            o.par.resolutionw, o.par.resolutionh = nx, ny
    c.op("cube").cook(force=True)
    return T.shape


def set_volume(theta=0.0, stretch=1.0, step=1.0, interp=1, tau=0.0, emit=1.0, mip=0, tf=0, k=3.0,
               dof=0.0, dof_samples=64, light=0.0, shadow_tau=1.0, shadow_step=2.0):
    c = op("/project1/cinecube")
    m = _meta(c.fetch("cube_key"))
    nz, ny, nx = m["shape_zyx"]
    dv, tmax = m["dv_kms"], c.fetch("cube_Tmax")
    kappa = tau / (tmax * dv) if tau else 0.0            # track a: tau / (max T * dv)
    kshadow = shadow_tau / (tmax * dv) if light else 0.0
    _uniforms(c.op("render"), [("uDim", (nx, ny, nz, m["sigma_K"])), ("uCam", (theta, stretch, step, interp)),
                               ("uPhys", (dv, kappa, emit, mip)), ("uTf", (tf, k, dof, dof_samples)),
                               ("uLight", (light, kshadow, shadow_step, 0))])


def _cmap_ramp(name):
    # td has no matplotlib: the 256 entry tables are written by the python side (cinecube.td.sweep_td specs)
    return np.load(os.path.join(REPO, "results/td/cmaps.npz"))[name][None, :, :].astype(np.float32)


def set_post(scale=None, cmap="gray", bloom=0.0, gamma=1.0, grade=0.0, vignette=0.0, grain=0.0, seed=1):
    c = op("/project1/cinecube")
    if scale is None:
        scale = c.fetch("plain_scale", 1.0)
    _uniforms(c.op("display"), [("uDisp", (1.0 / scale, 0, 0, 0))])
    c.store("cmap_ramp_arr", np.ascontiguousarray(_cmap_ramp(cmap)))
    c.op("cmap_ramp").par.outputresolution = "custom"
    c.op("cmap_ramp").par.resolutionw, c.op("cmap_ramp").par.resolutionh = 256, 1
    c.op("cmap_ramp").cook(force=True)
    b = c.op("bloom"); b.bypass = bloom <= 0
    if bloom > 0:
        b.par.bloomintensity = bloom
    lv = c.op("exposure"); lv.bypass = gamma == 1.0
    lv.par.gamma1 = gamma
    gr = c.op("grade"); gr.bypass = grade <= 0
    _uniforms(gr, [("uGrade", (grade, 0, 0, 0))])
    vg = c.op("vignette"); vg.bypass = vignette <= 0
    _uniforms(vg, [("uVig", (vignette, 0, 0, 0))])
    gn = c.op("grain"); gn.bypass = grain <= 0
    nz = c.op("grain_noise")
    nz.par.type = "random"; nz.par.mono = True; nz.par.seed = seed
    nz.par.amp = grain * GRAIN_AMP_PER_STD
    nz.par.offset = 0.0


def render_volume(out_npy, **knobs):
    set_volume(**knobs)
    g = op("/project1/cinecube/render")
    g.cook(force=True)
    a = g.numpyArray(delayed=False)            # (h, w, 4) float32, row 0 = bottom of the image (= track a's origin lower)
    os.makedirs(os.path.dirname(out_npy), exist_ok=True)
    np.save(out_npy, a[..., 0].astype(np.float32))
    return a


def render_post(out_npy, scale, **post):
    set_volume()
    set_post(scale=scale, **post)
    c = op("/project1/cinecube")
    for n in ("render", "display", "cmap_ramp", "colormap", "bloom", "exposure", "grade", "vignette", "grain_noise", "grain", "OUT"):
        c.op(n).cook(force=True)
    a = c.op("OUT").numpyArray(delayed=False)
    os.makedirs(os.path.dirname(out_npy), exist_ok=True)
    np.save(out_npy, a[..., :3].astype(np.float32))
    return a


def render_frame(out_npy, **knobs):        # kept for the gate
    a = render_volume(out_npy, **knobs)
    json.dump(dict(knobs, cube=op("/project1/cinecube").fetch("cube_key"), renderer="touchdesigner glsl raymarch",
                   td_build=app.build, glsl=GLSL), open(out_npy.replace(".npy", "_spec.json"), "w"), indent=1)
    return a.shape


def run_specs(path=None, only=None):
    path = path or os.path.join(REPO, "results/td/specs.json")
    specs = json.load(open(path))
    t0, done, cur = time.time(), 0, None
    log = []
    for sp in specs:
        if only and sp["cube"] not in only:
            continue
        if sp["cube"] != cur:
            load(sp["cube"]); cur = sp["cube"]
        out = os.path.join(REPO, sp["raw"])
        t = time.time()
        if sp["kind"] == "volume":
            render_volume(out, **sp["knobs"])
        else:
            render_post(out, sp["scale"], **sp["knobs"])
        log.append(dict(tag=sp["tag"], cube=sp["cube"], seconds=round(time.time() - t, 4)))
        done += 1
    set_volume(); set_post(scale=1.0)
    json.dump(dict(frames=done, seconds=round(time.time() - t0, 2), td_build=app.build, log=log),
              open(path.replace(".json", "_td_log.json"), "w"), indent=1)
    return done, round(time.time() - t0, 2)
