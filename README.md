<p align="center">
  <img src="assets/cover.png" alt="run-spec" width="340">
</p>

<h1 align="center">run-spec</h1>

<p align="center">
  A Claude Code skill that carries a specification to completion on its own.
</p>

---

You point it at a Markdown or HTML file — or just a sentence — and it derives an
**acceptance register** from it, cuts the work into packages, routes each package
to a model sized for its difficulty, harvests the branches those agents produce,
and keeps a live dashboard published while it runs.

One invocation is exactly one tick. For continuous operation:

```bash
/loop 10m /run-spec docs/SPEC-SEARCH.md
```

## Install

```bash
./install.sh          # symlinks into ~/.claude/skills/run-spec
```

Then, in any project:

```bash
/run-spec path/to/SPEC.md
```

Requires Claude Code with subagent support, `git`, and `python3` (standard
library only — no dependencies).

## Why a register

An autonomous run needs an answer to one question: *what does done mean?* Without
one it drifts into self-congratulation after about three ticks — every agent
reports success, the summary sounds great, and nothing is verifiable.

So the first tick does the expensive thing: it reads the spec in full and turns
every claim it makes about the finished state into a criterion with a **check
that can fail**, plus a **counter-check** — the case that must *not* trigger.
A criterion whose failure mode you cannot name is not a criterion; it's a wish.

Each criterion is also marked by what it depends on:

| | |
|---|---|
| `build` | An agent can close it here and now. **Only these count as progress.** |
| `data` | Needs real production data that isn't available. |
| `external` | Depends on a third party — a key, an account, an approval. |
| `operations` | Only measurable in production over time. |

The run ends when every `build` criterion is closed, and the closing report names
the others individually with the reason no agent could close them. 90 % is not
the target; 100 % of the buildable is.

## Before anything is dispatched

Tick 0 starts nothing. It sets up the conditions under which an unattended run
is allowed to mean something:

1. **Read the source in full** and derive the register from it — see
   [`reference/register.md`](reference/register.md). Ten to sixty criteria is
   healthy; more than that and the file is really several runs.
2. **Find out what the gate does *not* cover.** Test runners built on
   transpilers (`tsx`, `ts-node`, `swc`, `babel-jest`) typically do not
   typecheck — a type error lands invisibly. If the missing check is
   *measurably clean* on the current tree, it becomes part of the gate. If it is
   already red, it does not, because that hands every agent a failure that isn't
   theirs.
3. **Run the gate once.** Red at tick 0 is the tick's result. Nothing starts.
4. **Derive the worktree recipe** — the step people skip. Agents work in fresh
   git worktrees, and a fresh worktree is missing exactly what `.gitignore`
   excludes: `node_modules`, built workspace `dist/`, `.env`, local fixtures.
   Measured in a real project: 8 tests red in a worktree that were green in the
   main tree, none of it the agent's doing. So the recipe is derived once
   against a throwaway worktree, closing the gap one cause at a time until the
   pass count matches — and then goes into **every** brief verbatim, with the
   expected count and the instruction to stop if it doesn't match.

## What it actually does per tick

1. **Harvest** — read each agent branch's diff (read it, not count it), land what
   holds up, run the gate, commit on green. No branch is ever deleted.
2. **Reconcile** — fill in evidence: file path, test name, gate result. Half a
   check is open, with a better note — not a tick.
3. **Dispatch** — the register is a graph: each criterion records the files it
   touches (`seam`) and what must be done first (`depends_on`), so the tool
   computes what is startable instead of the orchestrator guessing. Cut the
   next package along one coherent seam and route it:

   | Complexity | Model |
   |---|---|
   | mechanical (rename, complete a table, a grep guard) | `haiku` |
   | one bounded test, a function on a known seam | `sonnet` |
   | half-built, wiring missing, salvage, diff review | `opus` |
   | new subsystem, several seams, nothing exists yet | `fable` |

4. **Display** — regenerate the dashboard and republish it to the same URL.
5. **Report** — what was harvested, landed, started. A quiet tick is a result.

Agents run in isolated git worktrees, commit on `run-spec/<run>/<criteria>`, and
are forbidden from touching the register.

## The graph does the bookkeeping

`seam` and `depends_on` are what keep an unattended run from stalling politely.
`status` computes, instead of the orchestrator recalling:

- **READY NOW** — open, dependencies met, seam free, nobody on it. If slots are
  free and this list isn't empty, the tick dispatches or the report says why not.
- **BLOCKED**, with the reason: which dependency, or which agent holds the file.
- **Broken references and cycles**, loudly. A criterion depending on a typo'd id
  waits forever and looks merely patient.

Two criteria on one seam never run at the same time — that is the entire reason
the field exists.

**Anything deferred becomes a criterion.** When a brief says "that part is
explicitly not your job", that work does not survive as a sentence in a prompt.
It goes into the register with its seam and its dependency, and the graph hands
it back the moment it becomes possible. A spec line was lost exactly this way
once: deferred in one brief, never recorded, found six ticks later by the
closing measurement.

## Open questions do not stop the run

A question becomes a decision with a reason, recorded in `waiting_on_you`, and
sits at the top of the dashboard — visible to overturn, but not blocking. When in
doubt the run takes the variant that is *measurable*, and the variant that makes
a failure *loud* rather than smoothing it over. It stops only if continuing would
break something unrecoverable.

## The part that surprised me

The brief every agent receives ends with this:

> If a criterion doesn't hold up against measurement, report the number you
> measured instead of hitting the one you were given. A reasoned no is the most
> valuable thing you can send back.

In the first real run — a 450-line spec, 33 criteria, 15 commits — that sentence
produced nine findings, and most of them were about the *specification*, not the
code:

- a distance the author had estimated rather than computed
- a headline finding that turned out to be an artifact of the author's own SQL,
  which normalised whitespace differently than production does
- a list of "third-party addresses in the tree" of which six of seven had
  already been filtered years ago
- a rule that, implemented literally, would have deleted three real company
  addresses — and would have looked like cleanup
- a section demanding a value be reported that another section says is never
  extracted
- a test that pinned the bug as *expected behaviour*, with a plausible comment
  explaining why it was unavoidable

The defect rate the spec set out to fix went from 29.0 % to 3.2 %, measured by a
script rather than estimated. But the specification errors were worth more than
the fix, and none of them would have surfaced if the agents had been told to
satisfy their criteria rather than test them.

## Where specs live

A spec is source — reviewed, diffed, blamed — so it belongs in the repository it
describes, under `specs/`. Run state does not; that stays outside, and the two
are never mixed.

The format is HTML for one reason: a single file can be both the document a
person reads and the structure a parser reads. Every machine field is written
exactly **once**, as a `data-` attribute, and the page renders it back with
`content: attr()` — abridged, but this is the real shape:

```html
<li class="crit">
  <span class="id" data-id="C03"></span>
  <p class="sentence">A reference letter without a heading is still detected.</p>
  <p class="check">fixtures/sample-7.html yields exactly 2 entries, both source='body'.</p>
  <p class="check counter">sample-3.html, which has no reference letter, yields 0.</p>
  <span class="chip" data-reachable="build"></span>
  <span class="chip" data-complexity="medium"></span>
  <span class="seam" data-seam="src/detect/references.ts"></span>
  <span class="chip" data-depends="C01"></span>
</li>
```

A value written twice — once for the eye, once for the parser — drifts, and the
drift stays invisible until a run acts on the stale half. Opened from disk it is
a readable document; published as an Artifact it is a link you can send someone.

Markdown is unchanged: `/run-spec docs/SPEC.md` works exactly as before. HTML is
what the folder is *for*, not a requirement it imposes.

### The workflow around the folder is specified, not built

[`specs/0001-spec-workflow.spec.html`](specs/0001-spec-workflow.spec.html) asks
for three things this repository does not have yet:

| | |
|---|---|
| `/spec-init` | Measure the gate, what the gate does not cover, and the worktree recipe **once**, and check them into `specs/spec.config.json` — so tick 0 reads them instead of deriving them on every run. They are properties of the project, not of the run. |
| `/new-spec` | Interview first — read the code as it is, ask only what changes the work — then write the document. A generator produces a beautiful page full of wishes. |
| `runspec.py --from-spec` | Parse the register out of the document instead of re-wording it out of prose. Same move as `seam`/`depends_on`: computed instead of guessed. |

So the first spec in this repo is the spec for its own next feature. That is
also the only honest way to find out whether the format survives contact with a
real run — and the register it produces will say so either way.

## Run state

Nothing of the *run* lives in your repository — the spec does, the state does
not. It sits under `~/.claude/runs/<project>/<run>/`, so no foreign checkout
gets polluted:

```
register.json    criteria, checks, seams, dependencies, evidence
run.json         tick, agents, worktree recipe, artifact URL, open questions
dashboard.html   generated from both — no number by hand
```

The tool that maintains it has no dependencies and is callable on its own:

```bash
scripts/runspec.py init --goal "…" [--source SPEC.md] [--gate "…"]
scripts/runspec.py status      # tally · agents · READY NOW · BLOCKED · cycles
scripts/runspec.py dash        # regenerate dashboard.html
scripts/runspec.py list        # runs for this project
scripts/runspec.py active <slug>
```

## Layout

```
SKILL.md              the tick, the routing table, the agent brief, the traps
reference/register.md how to turn a document into checkable criteria
scripts/runspec.py    run state + dashboard generator, no dependencies
specs/                this repo's own specs, in the format described above
install.sh            symlink into ~/.claude/skills
```

## What it does not do

- It does not replace reading the diff. The orchestrator reads every diff it
  lands, and the skill says so repeatedly, because the failure mode of an
  autonomous run is a plausible test that proves nothing.
- It does not run without a green gate. If the gate is already red at tick 0,
  that is the tick's result — nothing is dispatched.
- It does not guarantee the register is complete. It guarantees that what the
  register claims is evidenced, and that gaps are named rather than hidden.

## Licence

MIT
