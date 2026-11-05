"""envelope: first crossing along the grid, none / top / value, categorical ops, 2 param ops"""
from cinecube.envelope import envelope_for_card, crossing, to_markdown


def row(name, params, data, band="conditional", label=None):
    return dict(name=name, params=params, label=label or name, family="f", kind="k", expected_class="c",
                data_recovered=data, structure_kept=0.5, flux_visible=1.0, band=band)


def fake_card():
    bands = dict(preserving_min=0.99, conditional_min=0.90, structure_preserving_min=0.9, structure_conditional_min=0.5)
    rows = [row("reference", {}, 1.0, "preserving")]
    # monotone, crosses conditional between 0.5 and 1.0
    rows += [row("absorb", {"tau": t}, d) for t, d in ((0.1, 0.995), (0.25, 0.95), (0.5, 0.91), (1.0, 0.7))]
    # never leaves
    rows += [row("dof", {"sigma": s}, d) for s, d in ((1, 0.98), (2, 0.97), (4, 0.95))]
    # always out
    rows += [row("vignette", {"strength": s}, d) for s, d in ((0.25, 0.8), (0.5, 0.6))]
    # dips out and comes back: first crossing wins
    rows += [row("orbit", {"theta": t, "aspect": 1}, d) for t, d in ((0, 0.995), (10, 0.85), (20, 0.92), (30, 0.5))]
    rows += [row("orbit", {"theta": t, "aspect": 2}, d) for t, d in ((0, 0.995), (10, 0.95), (20, 0.92), (30, 0.5))]
    rows += [row("colormap", {"cmap": c}, d, b) for c, d, b in (("gray", 0.995, "preserving"), ("jet", 0.93, "conditional"))]
    rows += [row("log", {}, 0.8, "distorting")]
    return dict(cube="fake", bands=bands, rows=rows)


def test_crossing_cases():
    series = [row("a", {"x": v}, d) for v, d in ((1, 0.95), (2, 0.92), (3, 0.85))]
    assert crossing(series, "x", 0.90) == ("value", 2, series[1])
    assert crossing(series, "x", 0.99)[0] == "none"
    assert crossing(series, "x", 0.80) == ("top", 3, series[2])


def test_envelope_table():
    res = envelope_for_card(fake_card())
    by = {(e["operator"], tuple(sorted((e.get("fixed") or {}).items()))): e for e in res["entries"]}
    absorb = by[("absorb", ())]
    assert absorb["conditional"]["value"] == 0.5 and absorb["conditional"]["status"] == "value"
    assert absorb["preserving"]["value"] == 0.1
    assert absorb["monotone"]
    assert by[("dof", ())]["conditional"]["status"] == "top"
    assert by[("vignette", ())]["conditional"]["status"] == "none"
    # dip at theta 10 stops the envelope at 0 even though 20 is back inside
    o1 = by[("orbit", (("aspect", 1),))]
    assert o1["conditional"]["value"] == 0 and not o1["monotone"]
    o2 = by[("orbit", (("aspect", 2),))]
    assert o2["conditional"]["value"] == 20
    cm = by[("colormap", ())]
    assert cm["categorical"] and cm["conditional"]["inside"] == ["gray", "jet"] and cm["preserving"]["inside"] == ["gray"]
    log = next(e for e in res["entries"] if e["operator"] == "log")
    assert log["param"] is None and log["band"] == "distorting"
    md = to_markdown([res])
    assert "tau 0.5" in md and "top of grid" in md and "always out" in md
