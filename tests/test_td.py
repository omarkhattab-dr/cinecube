import numpy as np

from cinecube.td.sweep_td import expand, label, tag_for


def test_expand_maps_params_to_td_knobs():
    got = list(expand({"name": "orbit", "kind": "volume", "grid": {"theta": [0, 30], "aspect": [1, 2]}}))
    assert len(got) == 4
    assert got[-1] == ({"theta": 30, "aspect": 2}, {"theta": 30, "stretch": 2})
    (p, k), = expand({"name": "threshold", "kind": "volume", "knobs": {"tf": 3}, "grid": {"k": [2]}})
    assert k == {"tf": 3, "k": 2}
    (p, k), = expand({"name": "grain", "kind": "post", "grid": {"sigma": [0.03]}})
    assert k == {"grain": 0.03}            # grain sigma is the post knob, not the dof sigma
    (p, k), = expand({"name": "dof", "kind": "volume", "grid": {"sigma": [4]}})
    assert k == {"dof": 4}


def test_labels_and_tags():
    assert label("absorb", {"tau": 0.5}) == "TD Absorption, tau 0.5"
    assert label("light", {"strength": 0.7}).startswith("TD light")
    assert tag_for(7, "absorb", {"tau": 0.25}) == "007_absorb_tau0p25"
