# run-spec

A Claude Code skill that carries a specification to completion on its own.

You point it at a Markdown or HTML file — or just a sentence — and it derives an
**acceptance register** from it, cuts the work into packages, routes each package
to a model sized for its difficulty, harvests the branches those agents produce,
and keeps a live dashboard published while it runs.

One invocation is exactly one tick. For continuous operation:

```bash
/loop 10m /run-spec docs/SPEC-SEARCH.md
```

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
are forbidden from touching the register. Run state lives in
`~/.claude/runs/<project>/<run>/` — no foreign repository gets polluted.

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

## Layout

```
SKILL.md              the tick, the routing table, the agent brief, the traps
reference/register.md how to turn a document into checkable criteria
scripts/runspec.py    run state + dashboard generator, no dependencies
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
