# Deriving the register

The register is the **truth about "done"**. It is created once, in the first
tick, and afterwards only reconciled — never reworded to make a tick possible.

## Schema

`register.json`:

```json
{
  "goal": "One sentence. What is true at the end that is not true today?",
  "source": "/abs/path/SPEC-PLACES.md",
  "project": "/abs/path/repo",
  "gate": "pnpm test && pnpm exec tsc --noEmit",
  "criteria": [
    {
      "id": "C03",
      "group": "Detection",
      "criterion": "A reference letter without a heading is still detected.",
      "check": "Run fixtures/sample-7.html: references[] holds exactly 2 entries, both with source='body'. Counter-check: sample-3.html (no reference letter) yields 0.",
      "status": "open",
      "reachable": "build",
      "complexity": "medium",
      "seam": ["src/detect/references.ts"],
      "depends_on": ["C01"],
      "evidence": null,
      "note": null
    }
  ]
}
```

`status`: `open` · `running` · `met` · `dropped`
`reachable`: `build` · `data` · `external` · `operations`
`complexity`: `simple` · `medium` · `hard` · `very_hard`
`seam`: the files this criterion changes — used to detect collisions
`depends_on`: criterion ids that must be `met` first

## Seam and depends_on — let the machine do the bookkeeping

These two fields turn the register from a list into a graph, and `runspec.py
status` then computes what a person keeps getting wrong:

- **READY NOW** — open, dependencies met, seam free, nobody on it. If slots are
  free and this list isn't empty, the tick has to dispatch or say why not.
- **BLOCKED** — with the reason: which dependency, or which agent holds the seam.
- **broken references and cycles**, loudly. A criterion depending on a typo'd id
  waits forever and looks merely patient.

Fill `seam` with the files an agent would actually touch, not every file it
reads. Two criteria sharing a seam must not run at the same time — that is the
whole point of recording it.

Keep `depends_on` to real ordering constraints ("this cannot be checked until
that exists"), not to preferences about sequence. An over-constrained graph
serialises work that could have run in parallel.

**Anything you defer becomes a criterion.** When you cut a package and set part
of it aside — because another agent holds the file, because it needs something
that doesn't exist yet — that part does not survive as a sentence in a prompt.
Write it into the register with its seam and its dependency, and the graph will
hand it back the moment it becomes possible. A spec line lost exactly this way
in the run this skill was built from: deferred in one brief, never written down,
and only found six ticks later by the closing measurement.

## Where criteria come from

**From a file (MD/HTML):** read all of it. Every claim the file makes about the
finished state becomes a criterion. Headings and sections become the `group`.
A section that only supplies context yields no criterion — that is fine and
must not be padded.

**From a sentence:** first look at the current state in the code (actually open
the affected files), then cut the gap between today and the goal into checkable
pieces. A register built from imagination is worthless.

## The one test that matters

> **Can you name how this criterion would fail?**

If you cannot, it is not a criterion but a wish. Then either sharpen it until
it can fail — or record it as a `note` and set `reachable` honestly.

The `check` must name **a concrete call path**: which file, which command,
which input, which output. "Works correctly" is not a check. Wherever possible
it includes a **counter-check** — the case that must *not* trigger. Without one,
the function that always says yes passes too.

## Setting `reachable` honestly

| Value | Means |
|---|---|
| `build` | An agent can close this here and now. **Only these count toward progress.** |
| `data` | Needs real production data that isn't here. |
| `external` | Depends on a third party: access, key, account, approval. |
| `operations` | Only measurable in production over time (latency over days, error rates). |

When in doubt, **not** `build`. A criterion wrongly marked buildable sends an
agent at a task it cannot solve, and it will then build a stub that says yes.
That costs more than an honest gap.

## Size

**10 to 60 criteria** is healthy.

- Fewer than 10 → too coarse to cut packages and route models. Sharpen.
- More than 60 → the source file is really several runs. Split it and state
  which part this run takes.

## Complexity, for routing

Do not grade by importance — grade by **number of unknowns**:

- `simple` — location known, shape known, no decision to make.
- `medium` — location known, the solution needs thinking through.
- `hard` — several files, one seam unclear, or there is a half-build to
  understand first.
- `very_hard` — nothing exists yet, several subsystems involved.

## What does not belong in the register

- Criteria describing the construction instead of the result ("add function
  `X`"). A criterion describes what is **true on the outside**, not how it is
  built.
- Two things in one criterion ("… and also …"). Split them — otherwise half the
  evidence buys a whole tick.
- Anything already true. Look before you assume. A register that starts 40 %
  green because nobody checked is a lie with a head start.

## The register may grow

Nothing above forbids adding criteria mid-run — as long as they come from
**measurement**, not from ambition. A gap an agent found, a defect discovered in
passing, a spec line that turns out to be unimplemented: those belong in the
register, even though they make the run longer and the percentage worse.

The direction is the test. Adding a criterion because you measured something
undone is honest. Rewording one because it refuses to go green is not.

## When the spec is wrong

It will happen, and it is one of the more valuable things a run produces. A
specification is written before the code is run; the register is filled while
it runs. Real cases from one run:

- a distance the author had estimated rather than computed
- a headline finding that turned out to be an artifact of the author's own
  measurement query
- a list of "third-party addresses in the tree" of which most had already been
  filtered
- a rule that, implemented literally, would have deleted real data
- a section demanding a value be reported that another section says is never
  extracted

**Correct the criterion against the measurement, and record both** — the old
wording, the measured number, and why you changed it. That is the opposite of
massaging: it makes the register harder to satisfy and easier to trust.
