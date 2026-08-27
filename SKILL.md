---
name: run-spec
description: Autonomously implements a task or a spec file (Markdown/HTML) — derives an acceptance register from it, cuts work packages, routes them by complexity across haiku/sonnet/opus/fable, harvests their branches and keeps a live dashboard published as an Artifact. One invocation is exactly one tick; built for continuous operation with `/loop /run-spec <file-or-task>`. Invoke it when a larger piece of work should be carried to completion unattended — in any project.
---

# run-spec

One invocation = **one tick**. Not the whole job, not a single move:
harvest, reconcile, dispatch, display, report. Then stop.

Every tick must be **correct on its own**. It may not assume any state in your
head that the previous tick left behind. Everything that survives between two
ticks lives in `register.json`, `run.json` and in git.

This skill spawns subagents. That is its purpose, not an exception.

The tool for run state and display (executable, call it directly — **no**
`R="..."` alias, zsh does not word-split variables):

```bash
~/.claude/skills/run-spec/scripts/runspec.py status
```

Run state lives outside the project, under `~/.claude/runs/<project>/<run>/`.
No foreign repository gets polluted.

---

## Tick 0 — Setup

`runspec.py status` says "No active run"? Then first:

### 1 · Pin the goal

If the invocation names a file (`/run-spec SPEC-PLACES.md`), that file is the
source — **read all of it**, don't skim. If it names only a sentence, that
sentence is the goal.

### 2 · Create the run

`runspec.py init --goal "<one sentence>" [--source <file>]`. This also guesses
the gate (`test`/`check`/`verify`…). If the guess is wrong: `--gate "<command>"`.

### 3 · Find out what the gate does *not* cover

**A green gate is not the same as a correct build.** Look at what the gate
command actually runs. Test runners built on transpilers (`tsx`, `ts-node`,
`swc`, `babel-jest`) typically **do not typecheck** — a type error lands
invisibly. The same goes for lint and format.

If a check is missing and running it on the current tree is **measurably
clean**, extend the gate and record it. If it is already red, do not extend —
you would be handing every agent a failure that isn't theirs.

### 4 · Run the gate once, before anyone builds

If it is already red, that is this tick's result — report it and start nothing.
A run on a red gate makes every agent hunt for a bug that was already there.

### 5 · Derive the worktree recipe — the step people skip

Agents work in fresh git worktrees. A fresh worktree does **not** have what
`.gitignore` excludes, and that is usually exactly what the test suite needs.
Measured in a real project: 8 tests were red in a worktree that were green in
the main tree, and none of it was the agent's doing.

**Derive the recipe once, yourself, and write it into `run.json`:**

1. Create a throwaway worktree: `git worktree add --detach /tmp/probe HEAD`
2. Run the gate there. Same number of passes as the main tree? Then you're done.
3. If not, close the gap one cause at a time, and **read the actual error**
   instead of guessing. The usual suspects, in the order they bite:
   - **no `node_modules`** → the package manager's install
   - **workspace dependencies not built** — `dist/` is gitignored, so
     `packages/*/dist` is missing (`pnpm --filter "<app>^..." build` or the
     monorepo's equivalent)
   - **`.env` missing** → copy it from the main tree by absolute path
   - **local state missing** — a database, a fixture directory, a cache. Look
     for a migration or seed command before you copy files.
4. Repeat until the gate reports **the same numbers as the main tree**.
5. `git worktree remove --force /tmp/probe`

The recipe goes into **every** agent brief, verbatim, together with the
expected pass count and the instruction to stop if the count doesn't match.
Without that sentence each agent discovers this alone, and one of them won't.

### 6 · Derive the register

Read `reference/register.md` and follow it. This is the most expensive and most
important step. Without an honest register the run tips into
self-congratulation after three ticks.

### 7 · Set `run.json`

`push_allowed` only `true` if the project's CLAUDE.md explicitly permits
pushing directly. Check `max_agents` (default 4) and `base_branch`.

Then continue with steps 4 and 5 of the tick (display + report).

---

## The tick

### 0 · Situation

```bash
~/.claude/skills/run-spec/scripts/runspec.py status
```

The **honest work list is only the `reachable: build` ones.** Everything else
(`data`, `external`, `operations`) gets named, not hidden, not massaged.

### 1 · Harvest — what got finished since the last tick?

Every agent commits on `run-spec/<run>/<criteria>`. Branches carrying work:

```bash
RUN=$(basename "$(~/.claude/skills/run-spec/scripts/runspec.py where)"); BASE=$(git rev-parse --abbrev-ref HEAD)
git for-each-ref --format='%(refname:short)' "refs/heads/run-spec/$RUN/*" |
  while read -r b; do n=$(git rev-list --count "$BASE..$b" 2>/dev/null || echo 0)
    [ "$n" != "0" ] && echo "$n  $b"; done
```

For each branch with new work:

1. `git diff --stat "$BASE...<branch>"` — real work or just noise?
2. **Read the diff, don't count it.** A test that constructs its own input is
   not evidence. Neither is a test that measures a rebuild instead of the real
   seam. What fails that reading does not get landed; it goes back with a
   reason (`state: "returned"`).
3. `git cherry-pick --no-commit <sha>` or `git merge --no-commit`.
4. **Run the gate. Green ⇒ commit immediately.** Don't accumulate. Push only if
   `push_allowed`.
5. **No branch is ever deleted.** Not even after a successful merge.

### 2 · Reconcile — the register

For every landed package: set `status` to `met` and fill `evidence` with
**file path + test name + gate result**. Otherwise it stays open.

**A criterion goes green only when the whole check is evidenced.** Half a check
is open — with a better note, not with a tick. The entire value of the register
hangs on this. Never set a tick whose evidence you don't believe yourself.

**Before crediting anything, ask whether it was already true.** A criterion
derived from prose may describe a problem the code fixed long ago. Measure
before you credit — a register that starts at 40 % green because nobody looked
is a lie with a head start.

### 3 · Dispatch — the next package

If fewer than `max_agents` are running, add one. Sizing: **one package = one
coherent seam**, big enough for a context window, no bigger. Criteria sharing a
seam belong in **one** package, or the branches collide.

| Complexity | Model | For |
|---|---|---|
| `simple` | `haiku` | purely mechanical: rename, complete a table, a grep guard, text without logic |
| `medium` | `sonnet` | one well-bounded test, a function on a known seam, structural refactor |
| `hard` | `opus` | half-built, wiring or measurement missing; salvage; supervision; diff review |
| `very_hard` | `fable` | new subsystem, several seams, none of it exists yet |

**Do not work out by hand what is startable — `status` computes it.** With
`seam` and `depends_on` filled in, it prints `READY NOW` (dependencies met,
seam free, nobody on it) and `BLOCKED` with the reason for each. It also names
broken dependency references and cycles, which otherwise look like patience.

If `READY NOW` is non-empty and slots are free, this tick dispatches — or the
report says why not. That sentence exists because the alternative is a
criterion nobody is working on that nobody notices.

**Anything you defer becomes a criterion.** When you tell an agent "that part
is explicitly not your job" — because another agent holds the file, because it
needs something that doesn't exist yet — that work does not survive as a
sentence in a brief. Write it into the register with its seam and dependency.
A spec line was lost exactly this way once: deferred in one brief, never
recorded, found six ticks later by the closing measurement.

Start the agent with `isolation: "worktree"`, `model` from the table, `name` =
package name. Then update `run.json` → `agents[]` with
`name/model/package/criteria/since` and `state: "running"`, and set those
criteria to `running` in the register.

**Brief template** — a subagent sees only its brief, never this conversation:

> **Step 0 — branch and environment, in this order.** Without these steps N
> tests are red that have nothing to do with you, and you will hunt your own
> ghost. This is verified, not assumed:
> `git switch -c run-spec/<run>/<ids> <base_branch>`, then *<the recipe from
> `run.json`, verbatim>*.
> **Check before your first change:** `<gate>` must report **<N> pass / 0
> fail**. If it reports anything else, your environment is broken and not the
> code — say so and stop.
>
> **Goal:** <criterion verbatim> — **Check:** <check verbatim>.
> **Context:** <the 3–5 files this touches> · <the relevant traps>.
> **Gate:** `<command>` — must be green.
> **Forbidden:** touching the register or run state. Rewording criteria.
> Deleting branches. Touching seams other than the one named.
> **Commit the moment it first goes green.** Don't accumulate, don't push.
>
> **If a criterion doesn't hold up against measurement, report the number you
> measured instead of hitting the one you were given.** A reasoned no is the
> most valuable thing you can send back. Criteria are written by someone who
> has not run the code; you have.

That last paragraph is not politeness. In one real run it produced six
findings, including a spec line that would have deleted three real company
addresses while looking like cleanup.

### 4 · Display — the dashboard

Maintain `run.json`: `tick` +1, `state` (one sentence on what is true right
now), `agents[].state`, append to `log`. Then:

```bash
~/.claude/skills/run-spec/scripts/runspec.py dash
```

This generates `dashboard.html` from register + run state — **no number by
hand.** Then publish it with the `Artifact` tool:

- `file_path` = the printed path, `favicon: "📋"`, `label: "Tick <n>"`
- **`url`** = `artifact_url` from `run.json`, if set. Without that parameter
  every tick creates a *new* artifact and the tab you have open never updates.
- On the first publish, write the returned URL into `run.json` →
  `artifact_url` and **name it in your report**.

### 5 · Report

One short paragraph: harvested, landed, started, where things stand, plus the
artifact URL. If nothing moved, say so — a quiet tick is a result, not a reason
to invent one.

---

## Open questions

**Decide, justify, keep going.** A question does not stop the run. It goes into
`run.json` → `waiting_on_you` as `{"question": "...", "decision": "... because ..."}`
and thereby sits at the top of the dashboard — visible to overturn, but not
blocking.

When in doubt: the variant that is **measurable**. The variant that makes a
failure **loud** instead of smoothing it over.

Stop only if continuing breaks something that cannot be recovered.

**When two agents need the same answer, answer it once and send it to both.**
Otherwise they answer it differently and their branches contradict each other.

---

## When your measurement contradicts an agent's

It happens, and it matters how you handle it. Reopening a criterion on a
disputed claim is right. But before you do:

**Check your own instrument first.** Reading a structure that doesn't exist
returns `undefined`, and `undefined` looks exactly like "nothing was
produced". In one run the orchestrator reached for three fields that were not
there — `tree.values['locations']`, `dump.blocks`, `agent_runs.version` — and
concluded from the resulting emptiness that two criteria had regressed.

If the disagreement survives that, prefer the **apparatus built for the job**
over an ad-hoc replay: a fixture whose scope is verified against the source
data beats a script you wrote five minutes ago. Ask a second, independent agent
before you decide. And if you decide without an explanation, say so — record
the unresolved thread against a later criterion that walks the same path.

---

## Traps that have already cost money

- **A test that constructs its own input tests the assumption it is meant to
  prove.** The most expensive trap there is.
- **A test can pin the bug.** The worst version of the above: a test asserting
  the defect as expected behaviour, with a plausible comment explaining why it
  is unavoidable. It turns the repair into a regression. When a fix makes an
  old test red, read that test before you believe it.
- **"Built, tested, called by no production path."** A request in a prompt is
  not fulfilment. The evidence has to walk the real call path.
- **A measurement that normalises text differently than production does not
  measure production.** A query that replaces newlines, strips tags or
  lowercases will report findings the running system never produces. Check that
  the measuring instrument sees what production sees.
- **An untracked red test file makes the gate red for everyone.** Before any
  debugging: `git status --short` — untracked test files?
- **A wall-clock threshold measures the machine, not the code.** Under the
  parallel load of a full suite, a tight budget flakes. Measure the claim
  structurally where you can; if you keep a timing check, make it a ratio
  within one run, never an absolute number. A flaky test in a continuous run
  gets blamed on the next agent, who did not cause it.
- **A small model imitates the prompt:** `haiku` copies negative examples and
  appends rule lists verbatim. Mechanical work without prose output only.
- **Parallel sessions in the main working tree destroy uncommitted work.**
  Write your own out before agents start.
- **Two agents on one seam** produce conflicts nobody resolves. Check for file
  overlap when you cut packages.

---

## When the run ends

When **all `reachable: build` criteria are closed**. Then write the closing
report: what was built, and the remaining `data`/`external`/`operations` ones
**by name**, with the reason no agent can close them. Then end the loop.

Do not end because a number looks good. 90 % is not the target; 100 % of the
buildable is.
