import json
import os
import sys

try:
    import hou
except ImportError:
    sys.exit("this runs inside hython, not plain python")


def setp(node, candidates, value):
    for name in candidates:
        p = node.parm(name) or node.parmTuple(name)
        if p is not None:
            try:
                p.set(value)
                return name
            except Exception as e:
                print("  could not set %s.%s = %r: %s" % (node.path(), name, value, e))
    print("  NONE of these parms exist on %s (%s): %s. value %r not set" % (node.path(), node.type().name(), candidates, value))
    return None


def build(spec):
    vdb = spec["vdb"]
    meta = json.load(open(spec.get("meta") or vdb.replace(".vdb", ".json")))
    nz, ny, nx = meta["shape_zyx"]
    stretch = float(spec.get("stretch", 1.0))
    res = spec.get("resolution") or [nx, ny]
    out = spec["out"]
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)

    obj = hou.node("/obj")
    for n in ("cinecube", "cam"):
        if obj.node(n):
            obj.node(n).destroy()
    geo = obj.createNode("geo", "cinecube")
    f = geo.createNode("file", "vdb"); f.parm("file").set(os.path.abspath(vdb))
    xf = geo.createNode("xform", "stretch"); xf.setInput(0, f); xf.parmTuple("s").set((1.0, 1.0, stretch))
    outn = geo.createNode("null", "OUT"); outn.setInput(0, xf); outn.setDisplayFlag(True); outn.setRenderFlag(True)
    geo.layoutChildren()

    mat = hou.node("/mat")
    if mat.node("plain"):
        mat.node("plain").destroy()
    shader = None
    for typ in ("kma_pyroshader", "pyroshader::3.0", "pyroshader::2.0", "pyroshader"):
        try:
            shader = mat.createNode(typ, "plain"); break
        except hou.OperationFailed:
            continue
    if shader is None:
        print("  no pyro shader type found in /mat, build the material by hand")
    else:
        print("  material: %s" % shader.type().name())
        setp(shader, ["s_densityscale", "smokedensity", "densityscale"], float(spec.get("absorption", 0.0)))
        setp(shader, ["s_scatterscale", "scatterscale", "scattering"], float(spec.get("scatter", 0.0)))
        setp(shader, ["s_phase", "phase", "anisotropy"], float(spec.get("anisotropy", 0.0)))
        setp(shader, ["fi_field", "fe_field", "emissionfield", "firefield"], "density")
        setp(shader, ["fi_int", "fe_int", "emissionscale", "fireintensity"], float(spec.get("emission_scale", 1.0)))
        setp(shader, ["fe_colormode", "fi_colormode", "colormode"], 0)
        geo.parm("shop_materialpath").set(shader.path())

    cam = obj.createNode("cam", "cam")
    cam.parm("projection").set(1)
    cam.parm("orthowidth").set(float(nx))
    cam.parmTuple("res").set((int(res[0]), int(res[1])))
    cam.parm("aspect").set(1.0)
    far = nz * stretch + 200.0
    cam.parmTuple("t").set((nx / 2.0, ny / 2.0, nz * stretch + 100.0))
    theta = float(spec.get("theta_deg", 0.0))
    if theta:
        import math
        cx, cz = nx / 2.0, nz * stretch / 2.0
        r = nz * stretch / 2.0 + 100.0
        cam.parmTuple("t").set((cx + r * math.sin(math.radians(theta)), ny / 2.0, cz + r * math.cos(math.radians(theta))))
        cam.parmTuple("r").set((0.0, theta, 0.0))
    cam.parm("near").set(0.1); cam.parm("far").set(far * 2)
    dof = spec.get("dof")
    if dof:
        setp(cam, ["fstop"], float(dof.get("fstop", 2.8)))
        setp(cam, ["focus"], float(dof.get("focus", nz * stretch / 2.0 + 100.0)))

    light = spec.get("light")
    if light:
        ln = obj.createNode("hlight::2.0", "sun")
        setp(ln, ["light_type"], 7 if light.get("kind", "sun") == "sun" else 0)
        setp(ln, ["light_intensity"], float(light.get("intensity", 1.0)))
        ln.parmTuple("r").set(tuple(light.get("rotate", [45.0, 30.0, 0.0])))

    outc = hou.node("/out")
    if outc.node("karma"):
        outc.node("karma").destroy()
    rop = None
    for typ in ("karma", "karma::2.0"):
        try:
            rop = outc.createNode(typ, "karma"); break
        except hou.OperationFailed:
            continue
    if rop is None:
        print("  no karma rop in /out, render by hand")
        return None
    print("  rop: %s" % rop.type().name())
    setp(rop, ["camera"], cam.path())
    setp(rop, ["picture", "vm_picture", "outputimage"], os.path.abspath(out) + ".exr")
    setp(rop, ["resolutionx", "res_overridex", "resx"], int(res[0]))
    setp(rop, ["resolutiony", "res_overridey", "resy"], int(res[1]))
    setp(rop, ["override_camerares", "res_override"], 1)
    setp(rop, ["samplesperpixel", "pathtracedsamples", "vm_samples"], int(spec.get("samples", 64)))
    setp(rop, ["volumesteprate", "vm_volumesteprate", "volumestepsize"], float(spec.get("volume_step", 0.5)))
    setp(rop, ["engine", "renderengine"], spec.get("engine", "cpu"))
    setp(rop, ["denoiser", "usedenoiser"], 0)
    setp(rop, ["enablemblur", "motionblur"], 0)
    setp(rop, ["disablelighting"], 0)
    json.dump(spec, open(out + "_spec.json", "w"), indent=1)
    return rop


def main(argv):
    if not argv:
        sys.exit("usage: hython scene.py spec.json [--hip only] [--hip path.hip]")
    spec = json.load(open(argv[0]))
    rop = build(spec)
    hip = spec["out"] + ".hip"
    if "--hip" in argv:
        i = argv.index("--hip")
        if i + 1 < len(argv) and argv[i + 1] != "only":
            hip = argv[i + 1]
    hou.hipFile.save(hip)
    print("saved %s" % hip)
    if rop is not None and "only" not in argv:
        print("rendering %s ..." % spec["out"])
        rop.render(verbose=True)
        print("done")


if __name__ == "__main__":
    main(sys.argv[1:])
