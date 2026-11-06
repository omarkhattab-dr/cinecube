"""track B lives here: cube -> vdb -> houdini (karma) -> png/exr -> the same reader as track A.
export_vdb.py  numpy -> npz (+ vdb if the openvdb python bindings are around)
npz_to_vdb.py  runs in hython, npz -> vdb with houdinis own volume tools (no bindings needed)
scene.py       runs in hython, builds the plain scene from a json spec and renders it
gate.py        plain render vs moment0, the zero point check. runs here, no houdini needed
"""
