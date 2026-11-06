"""
scene.py - runs INSIDE hython. builds the houdini scene for one spec and renders it with karma.

    hython cinecube/houdini/scene.py cinecube/houdini/specs/plain_l1448.json
    hython cinecube/houdini/scene.py cinecube/houdini/specs/plain_l1448.json --hip only   # just save the .hip, render by hand

FIRST RUN NOTE (arash): this was written without a houdini to test on. the obj side (geo, file sop,
ortho camera) uses parms that have been the same since forever. the karma side (rop + shader) uses
parm names from h20 and a helper that tries a few names and prints what it found, so if a parm name
is wrong you get a clear line, not a crash. send me the printout of the first run and ill fix names.
the manual recipe in README.md is the same scene node by node, use it to check.

the scene, from the spec:
    /obj/cinecube        geo: file sop -> the vdb. material from /mat
    /obj/cam             orthographic camera looking down -z at the whole x y field, 1 px per voxel
    /mat/plain           emission only volume shader (density -> emission, no absorption, no scatter)
    /out/karma           karma rop: this camera, this resolution, linear exr out, no lights

the spec (json) has the knobs. all of them default to "off", and off = the gate scene:
    absorption      0        density * this = absorption density. 0 = emission only
    scatter         0        scattering density. 0 = none
    anisotropy      0        -1..1, only matters with scatter
    emission_scale  1.0      k in emission = k * density. any value is fine, the gate fits it
    theta_deg       0        camera orbit about the y axis, 0 = straight down -z
    stretch         1        voxel size along z (velocity). the vdb was exported at 1, this scales the geo
    samples         64       pixel samples
    volume_step     0.5      volume step rate / size (smaller = more accurate, the gate finds the limit)
    light           null     {"kind": "sun", "intensity": 1, "rotate": [45, 30, 0]}, null = no light at all
    dof             null     {"fstop": 2.8, "focus": 60}, null = pinhole
    resolution      [nx, ny] pixels, default from the json next to the vdb (1 px per voxel)
"""
import json
import os
import sys

try:
    import hou
except ImportError:
    sys.exit("this runs inside hython, not plain python")


def setp(node, candidates, value):
    """set the first parm name that exists. prints when none does so a wrong name is loud not silent"""
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

    # ---- geometry: the vdb, scaled along z by the stretch
    obj = hou.node("/obj")
    for n in ("cinecube", "cam"):
        if obj.node(n):
            obj.node(n).destroy()
    geo = obj.createNode("geo", "cinecube")
    f = geo.createNode("file", "vdb"); f.parm("file").set(os.path.abspath(vdb))
    xf = geo.createNode("xform", "stretch"); xf.setInput(0, f); xf.parmTuple("s").set((1.0, 1.0, stretch))
    outn = geo.createNode("null", "OUT"); outn.setInput(0, xf); outn.setDisplayFlag(True); outn.setRenderFlag(True)
    geo.layoutChildren()

    # ---- material: emission only volume. see README for the manual version of the same thing
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
        print("  no pyro shader type found in /mat, build the material by hand (README)")
    else:
        print("  material: %s" % shader.type().name())
        setp(shader, ["s_densityscale", "smokedensity", "densityscale"], float(spec.get("absorption", 0.0)))      # smoke = absorption, 0 = none
        setp(shader, ["s_scatterscale", "scatterscale", "scattering"], float(spec.get("scatter", 0.0)))
        setp(shader, ["s_phase", "phase", "anisotropy"], float(spec.get("anisotropy", 0.0)))
        setp(shader, ["fi_field", "fe_field", "emissionfield", "firefield"], "density")                            # emit from the density grid
        setp(shader, ["fi_int", "fe_int", "emissionscale", "fireintensity"], float(spec.get("emission_scale", 1.0)))
        setp(shader, ["fe_colormode", "fi_colormode", "colormode"], 0)                                              # constant color, not blackbody
        geo.parm("shop_materialpath").set(shader.path())

    # ---- camera: orthographic, looking down -z, the whole x y field, 1 px per voxel
    cam = obj.createNode("cam", "cam")
    cam.parm("projection").set(1)                                   # 1 = orthographic
    cam.parm("orthowidth").set(float(nx))
    cam.parmTuple("res").set((int(res[0]), int(res[1])))
    cam.parm("aspect").set(1.0)
    far = nz * stretch + 200.0
    cam.parmTuple("t").set((nx / 2.0, ny / 2.0, nz * stretch + 100.0))
    theta = float(spec.get("theta_deg", 0.0))
    if theta:
        # orbit about the y axis through the volume centre: rotate, then move the camera accordingly
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

    # ---- light: none by default (emission only). a sun if the spec asks
    light = spec.get("light")
    if light:
        ln = obj.createNode("hlight::2.0", "sun")
        setp(ln, ["light_type"], 7 if light.get("kind", "sun") == "sun" else 0)
        setp(ln, ["light_intensity"], float(light.get("intensity", 1.0)))
        ln.parmTuple("r").set(tuple(light.get("rotate", [45.0, 30.0, 0.0])))

    # ---- render: karma rop in /out, linear exr, no color management (exr is scene linear anyway)
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
        print("  no karma rop in /out, render by hand (README)")
        return None
    print("  rop: %s" % rop.type().name())
    setp(rop, ["camera"], cam.path())
    setp(rop, ["picture", "vm_picture", "outputimage"], os.path.abspath(out) + ".exr")
    setp(rop, ["resolutionx", "res_overridex", "resx"], int(res[0]))
    setp(rop, ["resolutiony", "res_overridey", "resy"], int(res[1]))
    setp(rop, ["override_camerares", "res_override"], 1)
    setp(rop, ["samplesperpixel", "pathtracedsamples", "vm_samples"], int(spec.get("samples", 64)))
    setp(rop, ["volumesteprate", "vm_volumesteprate", "volumestepsize"], float(spec.get("volume_step", 0.5)))
    setp(rop, ["engine", "renderengine"], spec.get("engine", "cpu"))                                   # cpu is exact, xpu is fast
    setp(rop, ["denoiser", "usedenoiser"], 0)
    setp(rop, ["enablemblur", "motionblur"], 0)
    setp(rop, ["disablelighting"], 0)
    # the spec itself goes next to the render so the frame knows where it came from
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
