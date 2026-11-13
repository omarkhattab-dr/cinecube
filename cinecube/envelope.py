import argparse
import glob
import json
import os

NUMERIC = (int, float)


def _is_num(v):
    return isinstance(v, NUMERIC) and not isinstance(v, bool)


def groups_for(rows):
    params = [k for k in rows[0]["params"]]
    numeric = [k for k in params if _is_num(rows[0]["params"][k])]
    if not numeric:
        return []
    var = max(numeric, key=lambda k: len(set(r["params"][k] for r in rows)))
    if len(set(r["params"][var] for r in rows)) < 2:
        return []
    others = [k for k in params if k != var]
    out = {}
    for r in rows:
        key = tuple((k, r["params"][k]) for k in others)
        out.setdefault(key, []).append(r)
    return [(var, dict(k), sorted(v, key=lambda r: r["params"][var])) for k, v in out.items()]


def crossing(series, var, threshold, key="data_recovered"):
    inside = [r[key] >= threshold - 1e-9 for r in series]
    if not inside[0]:
        return "none", None, None
    if all(inside):
        return "top", series[-1]["params"][var], series[-1]
    k = inside.index(False) - 1
    return "value", series[k]["params"][var], series[k]


def envelope_for_card(card):
    bands = card["bands"]
    by_name = {}
    for r in card["rows"]:
        if r["name"] != "reference":
            by_name.setdefault(r["name"], []).append(r)
    out = []
    for name, rows in by_name.items():
        grps = groups_for(rows)
        if grps:
            for var, fixed, series in grps:
                entry = dict(operator=name, family=rows[0]["family"], param=var, fixed=fixed,
                             grid=[r["params"][var] for r in series],
                             data_recovered=[round(r["data_recovered"], 4) for r in series],
                             structure_kept=[round(r["structure_kept"], 4) for r in series],
                             flux_visible=[round(r["flux_visible"], 4) for r in series])
                for band_key, thr in (("conditional", bands["conditional_min"]), ("preserving", bands["preserving_min"])):
                    st, val, row = crossing(series, var, thr)
                    entry[band_key] = dict(status=st, value=val,
                                           scores=None if row is None else dict(data_recovered=round(row["data_recovered"], 4), structure_kept=round(row["structure_kept"], 4), flux_visible=round(row["flux_visible"], 4)),
                                           label=None if row is None else row["label"])
                d = entry["data_recovered"]
                entry["monotone"] = all(d[i] >= d[i + 1] - 1e-6 for i in range(len(d) - 1))
                out.append(entry)
        else:
            cats = [k for k in rows[0]["params"] if not _is_num(rows[0]["params"][k])]
            if cats and len(rows) > 1:
                var = cats[0]
                entry = dict(operator=name, family=rows[0]["family"], param=var, categorical=True,
                             grid=[r["params"][var] for r in rows],
                             data_recovered=[round(r["data_recovered"], 4) for r in rows],
                             conditional=dict(status="categorical", inside=[r["params"][var] for r in rows if r["band"] in ("conditional", "preserving")]),
                             preserving=dict(status="categorical", inside=[r["params"][var] for r in rows if r["band"] == "preserving"]))
                out.append(entry)
            else:
                r = rows[0]
                out.append(dict(operator=name, family=r["family"], param=None, band=r["band"],
                                scores=dict(data_recovered=round(r["data_recovered"], 4), structure_kept=round(r["structure_kept"], 4), flux_visible=round(r["flux_visible"], 4))))
    return dict(cube=card["cube"], bands=bands, entries=out)


def _fmt_env(e, band_key):
    b = e.get(band_key)
    if e.get("param") is None:
        return e["band"]
    if e.get("categorical"):
        return ", ".join(str(x) for x in b["inside"]) or "none"
    if b["status"] == "none":
        return "none (always out)"
    if b["status"] == "top":
        return "%s %s (top of grid, widen)" % (e["param"], b["value"])
    s = b["scores"]
    return "%s %s  (%.3f / %.3f / %.2f)" % (e["param"], b["value"], s["data_recovered"], s["structure_kept"], s["flux_visible"])


def to_markdown(results):
    lines = ["# envelopes, sweep v1", "",
             "biggest knob setting still inside the band (first crossing along the grid). scores at that setting",
             "= data recovered / structure kept / flux visible. none = even the smallest value is out. top = nothing",
             "in the grid leaves the band, widen it once. operators with no knob just show their band.", ""]
    for res in results:
        b = res["bands"]
        lines += ["## %s  (preserving >= %.3f, conditional >= %.3f)" % (res["cube"], b["preserving_min"], b["conditional_min"]), "",
                  "| operator | fixed | stay conditional | stay preserving | monotone |", "| --- | --- | --- | --- | --- |"]
        for e in res["entries"]:
            fixed = ", ".join("%s %s" % kv for kv in (e.get("fixed") or {}).items())
            mono = "" if e.get("param") is None or e.get("categorical") else ("yes" if e["monotone"] else "no")
            lines.append("| %s | %s | %s | %s | %s |" % (e["operator"], fixed, _fmt_env(e, "conditional"), _fmt_env(e, "preserving"), mono))
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="envelope per operator per object from the sweep json")
    ap.add_argument("results", nargs="?", default="results/v1")
    a = ap.parse_args(argv)
    results = []
    for p in sorted(glob.glob(os.path.join(a.results, "*", "scorecard.json"))):
        results.append(envelope_for_card(json.load(open(p))))
    json.dump(results, open(os.path.join(a.results, "envelope.json"), "w"), indent=1)
    md = to_markdown(results)
    open(os.path.join(a.results, "envelope.md"), "w").write(md)
    print(md)
    print("wrote", os.path.join(a.results, "envelope.json"), "and envelope.md")
    return results


if __name__ == "__main__":
    main()
