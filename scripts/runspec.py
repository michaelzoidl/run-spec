#!/usr/bin/env python3
"""run-spec — register, run state and dashboard for an autonomous build run.

The run state lives outside the project:
    ~/.claude/runs/<project>/<run>/{register.json,run.json,dashboard.html}

Commands:
    init --goal "<sentence>" [--source FILE] [--slug NAME] [--gate "npm test"]
    where            path of the active run
    list             every run of this project
    status           situation report (numbers + open buildable criteria)
    dash             regenerate dashboard.html
    active <slug>    make another run the active one
"""
import argparse
import datetime
import hashlib
import html
import json
import os
import re
import subprocess
import sys

RUNS = os.path.expanduser("~/.claude/runs")
STATUS = ("open", "running", "met", "dropped")
REACHABLE = ("build", "data", "external", "operations")


def slugify(text, fallback="run"):
    s = text.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return (s[:48].rstrip("-") or fallback)


def project_dir(cwd=None):
    cwd = os.path.abspath(cwd or os.getcwd())
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=cwd,
            capture_output=True, text=True, timeout=5).stdout.strip()
        if root:
            cwd = root
    except Exception:
        pass
    short = hashlib.sha1(cwd.encode()).hexdigest()[:6]
    return os.path.join(RUNS, f"{slugify(os.path.basename(cwd), 'project')}-{short}"), cwd


def active_file():
    return os.path.join(project_dir()[0], "ACTIVE")


def run_dir(slug=None, required=True):
    pdir, _ = project_dir()
    if slug is None:
        try:
            slug = open(active_file()).read().strip()
        except OSError:
            slug = None
    if not slug:
        if required:
            sys.exit("No active run. Start with `runspec.py init --goal \"...\"`.")
        return None
    d = os.path.join(pdir, slug)
    if required and not os.path.isdir(d):
        sys.exit(f"No run named {slug} under {pdir}")
    return d


def read(d, name, default=None):
    try:
        with open(os.path.join(d, name)) as f:
            return json.load(f)
    except OSError:
        return default


def write(d, name, data):
    p = os.path.join(d, name)
    with open(p, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return p


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def guess_gate(root):
    """The gate is the command that tells green from red.

    Note it usually does NOT typecheck — see SKILL.md, tick 0 step 3.
    """
    pkg = os.path.join(root, "package.json")
    if os.path.exists(pkg):
        try:
            scripts = json.load(open(pkg)).get("scripts", {})
        except Exception:
            scripts = {}
        pm = "pnpm" if os.path.exists(os.path.join(root, "pnpm-lock.yaml")) else \
             "yarn" if os.path.exists(os.path.join(root, "yarn.lock")) else "npm run"
        for cand in ("verify", "check", "ci", "test"):
            if cand in scripts:
                return f"{pm} {cand}".replace("npm run test", "npm test")
        parts = [f"{pm} {k}" for k in ("typecheck", "lint", "build") if k in scripts]
        if parts:
            return " && ".join(parts)
    for f, cmd in (("pyproject.toml", "pytest -q"), ("Cargo.toml", "cargo test"),
                   ("go.mod", "go test ./..."), ("Makefile", "make test")):
        if os.path.exists(os.path.join(root, f)):
            return cmd
    return ""


# ---------------------------------------------------------------- commands

def cmd_init(a):
    pdir, root = project_dir()
    if a.source and not os.path.isfile(a.source):
        sys.exit(f"Source not found: {os.path.abspath(a.source)}\n"
                 f"(looked relative to {os.getcwd()})")
    slug = a.slug or slugify(
        os.path.basename(a.source).rsplit(".", 1)[0] if a.source else a.goal)
    d = os.path.join(pdir, slug)
    os.makedirs(d, exist_ok=True)

    if read(d, "register.json") and not a.force:
        sys.exit(f"{d}/register.json already exists. --force overwrites.")

    write(d, "register.json", {
        "goal": a.goal,
        "source": os.path.abspath(a.source) if a.source else None,
        "project": root,
        "gate": a.gate if a.gate is not None else guess_gate(root),
        "created": now(),
        "criteria": [],
    })
    if not read(d, "run.json"):
        write(d, "run.json", {
            "tick": 0,
            "state": "created, register still empty",
            "artifact_url": None,
            "max_agents": 4,
            "push_allowed": False,
            "base_branch": subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root,
                capture_output=True, text=True).stdout.strip() or None,
            # Derived once in tick 0 and handed to every agent verbatim.
            # See SKILL.md, tick 0 step 5 — without it, agents chase ghosts.
            "worktree_recipe": [],
            "expected_gate_pass": None,
            "agents": [],
            "waiting_on_you": [],
            "log": [],
        })
    with open(active_file(), "w") as f:
        f.write(slug + "\n")
    print(d)


def cmd_where(a):
    print(run_dir(a.slug))


def cmd_active(a):
    run_dir(a.slug)
    with open(active_file(), "w") as f:
        f.write(a.slug + "\n")
    print(a.slug)


def cmd_list(a):
    pdir, _ = project_dir()
    cur = os.path.basename(run_dir(required=False) or "")
    if not os.path.isdir(pdir):
        return print("(no runs)")
    for name in sorted(os.listdir(pdir)):
        d = os.path.join(pdir, name)
        if not os.path.isdir(d):
            continue
        reg = read(d, "register.json", {})
        c = reg.get("criteria", [])
        done = sum(1 for x in c if x.get("status") == "met")
        print(f"{'*' if name == cur else ' '} {name:<40} {done}/{len(c)}  {reg.get('goal','')[:60]}")


def tally(criteria):
    live = [x for x in criteria if x.get("status") != "dropped"]
    buildable = [x for x in live if x.get("reachable", "build") == "build"]
    t = {
        "total": len(live),
        "met": sum(1 for x in live if x["status"] == "met"),
        "running": sum(1 for x in live if x["status"] == "running"),
        "dropped": len(criteria) - len(live),
        "buildable": len(buildable),
        "buildable_met": sum(1 for x in buildable if x["status"] == "met"),
        "buildable_open": [x for x in buildable if x["status"] == "open"],
        "not_buildable": {},
    }
    for x in live:
        r = x.get("reachable", "build")
        if r != "build" and x["status"] != "met":
            t["not_buildable"].setdefault(r, []).append(x["id"])
    return t


def cmd_status(a):
    d = run_dir(a.slug)
    reg, run = read(d, "register.json", {}), read(d, "run.json", {})
    c = reg.get("criteria", [])
    t = tally(c)
    print(f"RUN       {os.path.basename(d)}   tick {run.get('tick', 0)}")
    print(f"GOAL      {reg.get('goal','—')}")
    print(f"SOURCE    {reg.get('source') or '—'}")
    print(f"GATE      {reg.get('gate') or '— (none set!)'}")
    print(f"ARTIFACT  {run.get('artifact_url') or '— (not published yet)'}")
    if not run.get("worktree_recipe"):
        print("WORKTREE  — no recipe derived yet (see SKILL.md, tick 0 step 5)")
    if not c:
        return print("\nREGISTER EMPTY — derive criteria first (see reference/register.md).")
    print(f"\nBUILDABLE {t['buildable_met']}/{t['buildable']} met, "
          f"{t['running']} running, {len(t['buildable_open'])} open")
    print(f"TOTAL     {t['met']}/{t['total']}"
          + (f"  ({t['dropped']} dropped)" if t["dropped"] else ""))
    if t["not_buildable"]:
        print("NOT BUILDABLE  " + "  ".join(
            f"{r}:{len(v)}" for r, v in sorted(t["not_buildable"].items())))
    live = [ag for ag in run.get("agents", []) if ag.get("state") == "running"]
    print(f"\nAGENTS    {len(live)}/{run.get('max_agents', 4)} running")
    for ag in live:
        print(f"  · {ag.get('name','?'):<22} {ag.get('model','?'):<7} "
              f"{','.join(ag.get('criteria', [])):<14} {ag.get('package','')[:60]}")
    if t["buildable_open"]:
        print("\nOPEN AND BUILDABLE (this is the honest work list):")
        for x in sorted(t["buildable_open"], key=lambda x: (x.get("group", ""), x["id"])):
            print(f"  {x['id']:<8} [{x.get('complexity','?'):<9}] "
                  f"{x.get('group','')[:18]:<18} {x['criterion'][:70]}")
    if run.get("waiting_on_you"):
        print(f"\nWAITING ON YOU ({len(run['waiting_on_you'])}):")
        for q in run["waiting_on_you"]:
            print(f"  · {(q if isinstance(q, str) else q.get('question',''))[:100]}")
    if not t["buildable_open"] and not live:
        print("\n>>> ALL BUILDABLE CLOSED — write the closing report, end the loop.")


# ---------------------------------------------------------------- dashboard

CSS = """<style>
:root{
  --ground:#F4F6FA; --surface:#FFFFFF; --surface-2:#EAEFF7;
  --ink:#141922; --muted:#5A6577; --line:#DCE2EC;
  --accent:#2B4C9B; --accent-soft:#DFE7F6;
  --good:#1B7A4B; --warn:#9A6400; --critical:#B03024; --quiet:#96A0B0;
  --shadow:0 1px 2px rgba(20,25,34,.05),0 2px 10px rgba(20,25,34,.04);
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --ground:#0E1116; --surface:#161B23; --surface-2:#1D2430;
  --ink:#E4E9F2; --muted:#8792A5; --line:#262E3B;
  --accent:#7CA0F0; --accent-soft:#1C2842;
  --good:#4FBF83; --warn:#D9A036; --critical:#E5786C; --quiet:#66707E;
  --shadow:0 1px 2px rgba(0,0,0,.35),0 2px 12px rgba(0,0,0,.25);
}}
:root[data-theme="dark"]{
  --ground:#0E1116; --surface:#161B23; --surface-2:#1D2430;
  --ink:#E4E9F2; --muted:#8792A5; --line:#262E3B;
  --accent:#7CA0F0; --accent-soft:#1C2842;
  --good:#4FBF83; --warn:#D9A036; --critical:#E5786C; --quiet:#66707E;
  --shadow:0 1px 2px rgba(0,0,0,.35),0 2px 12px rgba(0,0,0,.25);
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:"IBM Plex Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  font-size:15px; line-height:1.55; -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1080px; margin:0 auto; padding:40px 24px 72px; display:flex; flex-direction:column; gap:28px}
h1,h2,h3,.label{font-family:"IBM Plex Sans Condensed","IBM Plex Sans",sans-serif}
h1{font-size:31px; font-weight:700; margin:0; letter-spacing:-.01em; text-wrap:balance}
h2{font-size:13px; font-weight:600; margin:0; text-transform:uppercase; letter-spacing:.11em; color:var(--muted)}
.label{font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:.1em; color:var(--muted)}
.mono{font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace; font-variant-numeric:tabular-nums}
.card{background:var(--surface); border:1px solid var(--line); border-radius:10px; box-shadow:var(--shadow)}
.sec{display:flex; flex-direction:column; gap:12px}

/* head */
.head{display:flex; flex-direction:column; gap:10px}
.eyebrow{display:flex; align-items:center; gap:10px; flex-wrap:wrap}
.eyebrow .tick{color:var(--accent)}
.goal{font-size:17px; color:var(--muted); max-width:62ch; margin:0; text-wrap:pretty}

/* meter */
.meter{display:flex; height:14px; border-radius:7px; overflow:hidden; background:var(--surface-2); border:1px solid var(--line)}
.meter span{display:block; height:100%}
.m-met{background:var(--good)}
.m-running{background:var(--accent)}
.m-open{background:var(--warn); opacity:.5}
.m-other{background:repeating-linear-gradient(45deg,var(--quiet),var(--quiet) 3px,transparent 3px,transparent 6px); opacity:.55}
.legend{display:flex; gap:18px; flex-wrap:wrap; font-size:12px; color:var(--muted)}
.legend b{color:var(--ink); font-weight:600}
.dot{display:inline-block; width:8px; height:8px; border-radius:2px; margin-right:6px; vertical-align:baseline}

/* tiles */
.tiles{display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px}
.tile{padding:14px 16px; display:flex; flex-direction:column; gap:2px}
.tile .num{font-size:30px; font-weight:600; line-height:1.1; letter-spacing:-.02em}
.tile .foot{font-size:12px; color:var(--muted)}
.t-good .num{color:var(--good)} .t-accent .num{color:var(--accent)}
.t-warn .num{color:var(--warn)} .t-quiet .num{color:var(--quiet)}

/* agents */
.agents{display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:12px}
.agent{padding:14px 16px; display:flex; flex-direction:column; gap:8px; position:relative; overflow:hidden}
.agent::before{content:""; position:absolute; left:0; top:0; bottom:0; width:3px; background:var(--accent)}
.agent .row{display:flex; align-items:center; gap:8px; flex-wrap:wrap}
.agent .name{font-weight:600}
.agent .package{font-size:13px; color:var(--muted); text-wrap:pretty}
.chip{font-size:11px; font-weight:600; letter-spacing:.04em; padding:2px 7px; border-radius:20px;
  background:var(--accent-soft); color:var(--accent); font-family:"IBM Plex Mono",monospace}
.chip.grey{background:var(--surface-2); color:var(--muted)}
.pulse{width:7px; height:7px; border-radius:50%; background:var(--accent); animation:pulse 2s ease-in-out infinite; flex:none}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
@media (prefers-reduced-motion:reduce){.pulse{animation:none}}

/* questions */
.question{padding:12px 16px; border-left:3px solid var(--critical); background:var(--surface);
  border-radius:0 8px 8px 0; border-top:1px solid var(--line); border-right:1px solid var(--line);
  border-bottom:1px solid var(--line); font-size:14px; text-wrap:pretty}
.question .answer{display:block; margin-top:6px; color:var(--muted); font-size:13px}

/* register */
.group{display:flex; flex-direction:column; gap:0; overflow:hidden}
.group .grouphead{display:flex; justify-content:space-between; align-items:center; gap:12px;
  padding:9px 16px; background:var(--surface-2); border-bottom:1px solid var(--line)}
.crit{display:grid; grid-template-columns:60px 1fr auto; gap:12px; align-items:start;
  padding:11px 16px 11px 13px; border-bottom:1px solid var(--line); border-left:3px solid transparent}
.crit:last-child{border-bottom:none}
.crit .id{font-size:12px; color:var(--muted)}
.crit .text{display:flex; flex-direction:column; gap:3px; min-width:0}
.crit .sentence{text-wrap:pretty}
.crit .evidence{font-size:12px; color:var(--muted); overflow-wrap:anywhere}
.crit .right{display:flex; gap:6px; align-items:center; flex-wrap:wrap; justify-content:flex-end}
.s-met{border-left-color:var(--good)}
.s-running{border-left-color:var(--accent); background:var(--accent-soft)}
.s-open{border-left-color:var(--warn)}
.s-dropped{opacity:.45}
.s-dropped .sentence{text-decoration:line-through}
.other{border-left-color:var(--quiet)}
.other .sentence{color:var(--muted)}
.check{color:var(--good); font-weight:600}

.empty{padding:22px 16px; color:var(--muted); font-size:14px}
.foot{display:flex; gap:20px; flex-wrap:wrap; font-size:12px; color:var(--muted);
  border-top:1px solid var(--line); padding-top:16px}
.foot code{font-family:"IBM Plex Mono",monospace; color:var(--ink)}
</style>"""

FONTS = ('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
         'family=IBM+Plex+Mono:wght@400;500;600&'
         'family=IBM+Plex+Sans+Condensed:wght@600;700&'
         'family=IBM+Plex+Sans:wght@400;500;600&display=swap">')

WHY = {"build": "", "data": "needs real data", "external": "depends on others",
       "operations": "only measurable in production"}


def e(x):
    return html.escape(str(x if x is not None else ""))


def tile(num, label, foot, cls):
    return (f'<div class="tile card {cls}"><div class="label">{e(label)}</div>'
            f'<div class="num mono">{e(num)}</div><div class="foot">{e(foot)}</div></div>')


def page_name(reg):
    """Short name for tab and gallery — never a sentence cut mid-word.

    An explicit "title" in the register wins. Otherwise the part of the goal
    before the first dash or colon: the thing itself is there, the explanation
    follows. Failing that, trim on a word boundary.
    """
    t = (reg.get("title") or "").strip()
    if not t:
        t = (reg.get("goal") or "Run state").strip()
        for sep in (" — ", " – ", " - ", ": "):
            if sep in t:
                t = t.split(sep)[0].strip()
                break
    if len(t) > 60:
        t = t[:60].rsplit(" ", 1)[0].rstrip(" ,;–—-") + "…"
    return t


def cmd_dash(a):
    d = run_dir(a.slug)
    reg, run = read(d, "register.json", {}), read(d, "run.json", {})
    c = [x for x in reg.get("criteria", []) if x.get("status") != "dropped"]
    t = tally(reg.get("criteria", []))
    n = max(len(c), 1)
    part = lambda k: round(100 * k / n, 2)
    n_met, n_run = t["met"], t["running"]
    n_open = len(t["buildable_open"])
    n_other = sum(len(v) for v in t["not_buildable"].values())

    o = [f"<title>{e(page_name(reg))}</title>", FONTS, CSS, '<div class="wrap">']

    o.append('<header class="head"><div class="eyebrow label">'
             f'<span class="tick mono">TICK {e(run.get("tick", 0))}</span>'
             f'<span>·</span><span>{e(os.path.basename(d))}</span>'
             + (f'<span>·</span><span class="mono">{e(os.path.basename(reg["source"]))}</span>'
                if reg.get("source") else "") + "</div>")
    o.append(f"<h1>{e(reg.get('goal', 'Run state'))}</h1>")
    if run.get("state"):
        o.append(f'<p class="goal">{e(run["state"])}</p>')
    o.append("</header>")

    o.append('<section class="sec"><h2>Progress</h2><div class="meter">'
             f'<span class="m-met" style="width:{part(n_met)}%"></span>'
             f'<span class="m-running" style="width:{part(n_run)}%"></span>'
             f'<span class="m-open" style="width:{part(n_open)}%"></span>'
             f'<span class="m-other" style="width:{part(n_other)}%"></span></div>'
             '<div class="legend">'
             f'<span><i class="dot" style="background:var(--good)"></i><b>{n_met}</b> met</span>'
             f'<span><i class="dot" style="background:var(--accent)"></i><b>{n_run}</b> in progress</span>'
             f'<span><i class="dot" style="background:var(--warn);opacity:.5"></i><b>{n_open}</b> open &amp; buildable</span>'
             f'<span><i class="dot" style="background:var(--quiet);opacity:.55"></i><b>{n_other}</b> not buildable</span>'
             "</div></section>")

    share = f"{round(100 * t['buildable_met'] / t['buildable']) if t['buildable'] else 0} %"
    live = [ag for ag in run.get("agents", []) if ag.get("state") == "running"]
    o.append('<section class="tiles">')
    o.append(tile(share, "Buildable closed", f"{t['buildable_met']} of {t['buildable']}", "t-good"))
    o.append(tile(f"{len(live)}", "Agents at work", f"of {run.get('max_agents', 4)} slots", "t-accent"))
    o.append(tile(f"{n_open}", "Waiting for an agent", "open and buildable", "t-warn"))
    o.append(tile(f"{n_other}", "No agent can close", ", ".join(
        f"{r} {len(v)}" for r, v in sorted(t["not_buildable"].items())) or "—", "t-quiet"))
    o.append("</section>")

    questions = run.get("waiting_on_you") or []
    if questions:
        o.append(f'<section class="sec"><h2>Decided — you can overturn ({len(questions)})</h2>')
        for q in questions:
            if isinstance(q, str):
                o.append(f'<div class="question">{e(q)}</div>')
            else:
                ans = q.get("decision") or q.get("answer")
                o.append(f'<div class="question">{e(q.get("question", ""))}'
                         + (f'<span class="answer">→ {e(ans)}</span>' if ans else "") + "</div>")
        o.append("</section>")

    o.append('<section class="sec"><h2>At work now</h2>')
    if live:
        o.append('<div class="agents">')
        for ag in live:
            ids = " ".join(ag.get("criteria", []))
            o.append('<article class="agent card"><div class="row"><span class="pulse"></span>'
                     f'<span class="name">{e(ag.get("name", "?"))}</span>'
                     f'<span class="chip mono">{e(ag.get("model", "?"))}</span>'
                     + (f'<span class="chip grey mono">{e(ids)}</span>' if ids else "")
                     + "</div>"
                     f'<div class="package">{e(ag.get("package", ""))}</div>'
                     + (f'<div class="label mono">since {e(ag["since"])}</div>' if ag.get("since") else "")
                     + "</article>")
        o.append("</div>")
    else:
        o.append('<div class="card empty">No agent running. The next tick dispatches.</div>')
    o.append("</section>")

    o.append('<section class="sec"><h2>Register</h2>')
    if not c:
        o.append('<div class="card empty">Register still empty — criteria are derived from the '
                 'source file in the first tick.</div>')
    groups = {}
    for x in c:
        groups.setdefault(x.get("group") or "Ungrouped", []).append(x)
    for name, rows in groups.items():
        done = sum(1 for x in rows if x["status"] == "met")
        o.append('<div class="group card"><div class="grouphead">'
                 f'<span class="label">{e(name)}</span>'
                 f'<span class="mono label">{done}/{len(rows)}</span></div>')
        for x in sorted(rows, key=lambda x: x["id"]):
            st = x.get("status", "open")
            reach = x.get("reachable", "build")
            classes = f"crit s-{e(st)}" + ("" if reach == "build" else " other")
            right = []
            if reach != "build":
                right.append(f'<span class="chip grey">{e(WHY.get(reach, reach))}</span>')
            elif st == "open":
                right.append(f'<span class="chip grey mono">{e(x.get("complexity", "?"))}</span>')
            elif st == "running":
                right.append('<span class="chip">in progress</span>')
            if st == "met":
                right.append('<span class="check">✓</span>')
            if st == "met":
                second = x.get("evidence")
            else:
                second = x.get("note") or (x.get("check") if st == "running" else None)
            o.append(f'<div class="{classes}" title="Check: {e(x.get("check", "—"))}">'
                     f'<div class="id mono">{e(x["id"])}</div>'
                     f'<div class="text"><div class="sentence">{e(x["criterion"])}</div>'
                     + (f'<div class="evidence">{e(second)}</div>' if second else "")
                     + f'</div><div class="right">{"".join(right)}</div></div>')
        o.append("</div>")
    o.append("</section>")

    o.append('<footer class="foot">'
             f'<span>As of {e(now())}</span>'
             + (f"<span>Gate <code>{e(reg['gate'])}</code></span>" if reg.get("gate") else "")
             + (f"<span>Base <code>{e(run['base_branch'])}</code></span>" if run.get("base_branch") else "")
             + f'<span>{"push allowed" if run.get("push_allowed") else "no push"}</span>'
             + "</footer></div>")

    p = os.path.join(d, "dashboard.html")
    with open(p, "w") as f:
        f.write("\n".join(o))
    print(p)


def main():
    p = argparse.ArgumentParser(prog="runspec")
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init"); i.set_defaults(fn=cmd_init)
    i.add_argument("--goal", required=True); i.add_argument("--source")
    i.add_argument("--slug"); i.add_argument("--gate"); i.add_argument("--force", action="store_true")
    for name, fn in (("where", cmd_where), ("status", cmd_status), ("dash", cmd_dash)):
        s = sub.add_parser(name); s.set_defaults(fn=fn); s.add_argument("--slug")
    s = sub.add_parser("list"); s.set_defaults(fn=cmd_list)
    s = sub.add_parser("active"); s.set_defaults(fn=cmd_active); s.add_argument("slug")
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
