"""Reconstruct the protected memory experiment in a fresh process without launching games."""
import argparse
from pathlib import Path

from . import run_memory_learning as run
from .outcome_rollouts import write


def reconstruct(root,declaration):
    decl,digest,banks=run.declaration(declaration)
    experiment=run.Experiment(root,decl,digest,banks,audit=True)
    try:
        return experiment.perform()
    except run.Incomplete as exc:
        experiment.evidence.finish()
        return incomplete_report(experiment.report,str(exc))


def incomplete_report(report,reason):
    report.update(status="inconclusive",reason=reason)
    report["counts"]={k:sum(b["counts"][k] for b in report["blocks"].values())
                      for k in ("assigned","attempted","completed","wins","failed","censored","invalid","unrun")}
    sealed=report["blocks"].get("sealed",{}).get("counts",{})
    report["transfer_executed"]=sealed.get("attempted",0)>0
    report["transfer_completed"]=sealed.get("completed",0)==288
    report["reinferred_decisions"]=sum(a.get("reinferred_decisions",0) for b in report["blocks"].values() for a in b["attempts"])
    report["maximum_declared_executions"]=3030
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",type=Path,required=True)
    parser.add_argument("--declaration",type=Path,default=run.ROOT/run.DECLARATION)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        report=reconstruct(args.run,args.declaration)
        write(args.output,report)
    except (OSError,ValueError,KeyError) as exc:
        parser.exit(1,"Memory reconstruction failed: "+str(exc)+"\n")
    print(report["status"],report["counts"],"reinferred",report["reinferred_decisions"])
    return 0


if __name__=="__main__":
    raise SystemExit(main())
