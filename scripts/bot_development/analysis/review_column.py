"""Summarize prolonged observations in a chosen map sector (default: Canyon shaft 54)."""
import argparse
import collections
import gzip
import json
from pathlib import Path
from analyze_speedvideo import unique_fresh
from analyze_trial import contains,sectors_from_numeric

def summarize(filepath, geometry, column=54):
    d=json.loads(gzip.decompress(filepath.read_bytes()))
    res=d["result"]
    start=res["recording_start_trace_seconds"]
    returned=res["recording_return_trace_seconds"]
    midpoint=(start+returned)/2
    end=start+res["capture"]["duration_seconds"]
    out={}
    for seat,obs in d["observations"].items():
        rs=[]
        for o in unique_fresh(obs):
            if not returned<=o["wall_seconds"]<=end:continue
            s=o["state"]
            sectors=tuple(g[0] for g in geometry if contains(s["position"],g))
            rs.append(dict(clip=round(o["wall_seconds"]-midpoint,3),game=s["game_time"],life=(o["world_epoch"],o["life_epoch"]),alive=s["health"]>0,position=s["position"],sectors=sectors,weapon=s["weapon"],ammo=s["ammo"],target=s["target"] is not None))
        episodes=[]
        prev=None
        for row in rs:
            key=row["sectors"] if row["alive"] else None
            continuous=prev and prev["life"]==row["life"] and row["clip"]-prev["clip"]<=.8 and 0<row["game"]-prev["game"]<=1
            if not episodes or episodes[-1]["sector"]!=key or not continuous:
                episodes.append({"life":row["life"],"sector":key,"start":row["clip"],"end":row["clip"],"continuous":bool(continuous),"n":0})
            episodes[-1]["end"]=row["clip"];episodes[-1]["n"]+=1;prev=row
        visits=[]
        for i,e in enumerate(episodes):
            if e["sector"]!=(column,) or e["end"]-e["start"]<6:continue
            previous=episodes[i-1]["sector"] if i>0 and e["continuous"] else None
            via=episodes[i-2]["sector"] if i>1 and e["continuous"] and episodes[i-1]["continuous"] else None
            visits.append(dict(life=e["life"],start=e["start"],end=e["end"],duration=round(e["end"]-e["start"],3),previous=previous,preceding=via))
        col=[r for r in rs if r["alive"] and r["sectors"]==(column,)]
        heavy=[r for r in rs if r["alive"] and (r["weapon"]==9 and r["ammo"]["power"]>=8 or r["weapon"]==7 and r["ammo"]["rail"]>=1)]
        out[seat]={f"pure_sector{column}_living_publications":len(col),f"pure_sector{column}_extended_spans":visits,"loaded_heavy_living_states":len(heavy),"loaded_heavy_with_target":sum(r["target"] for r in heavy),f"loaded_heavy_in_pure_{column}":sum(r["sectors"]==(column,) for r in heavy)}
    return {"label":res["label"],"seats":out}
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('traces', nargs='+', type=Path)
    parser.add_argument('--map', type=Path, required=True, help='Numeric export of your owned JKL')
    parser.add_argument('--sector', type=int, default=54, help='Sector to inspect; defaults to Canyon shaft 54')
    args = parser.parse_args()
    geometry = sectors_from_numeric(args.map)
    print(json.dumps([summarize(path, geometry, args.sector) for path in args.traces], indent=2))
