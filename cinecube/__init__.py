"""
cinecube - how far is a cinematic render from the actual data

main trick: render the cube plain (linear, no absorption, camera straight down the v axis)
and you get the moment 0 map exactly. so thats my zero point. everything cinematic
is an operator on top and i can score what it does.

files, same order as the pipeline:
    io        load cube, moment maps, noise, mask
    render    the ray marcher. reference render + all the camera/compositing stuff
    operators all the cinematic ops as plain functions + the registry the sweep reads
    decode    read data back out of a frame (colormap inversion)
    metrics   the 3 scores, controls, bands
    sweep     yaml in -> frames + json out -> scorecard
    synth     fake keplerian disk where i know the 3d truth
    index     velocity-as-depth index
    figures   paper figures from the json, nothing by hand
"""

__version__ = "0.2.0"
