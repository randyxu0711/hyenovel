# Task 8 Report — 運鏡家法 token 化

## What was implemented

1. **`web/src/theme.css`** — added, right after the type-scale (`--t-*`) block, inside `:root`:
   ```css
   --ease-house:cubic-bezier(.66,0,.2,1);
   --d-quick:.3s; --d-soft:.6s; --d-scene:.9s; --d-cam:1.4s;
   ```
   with the block comment specified in the brief (spec §3C, explains event curves are out of scope, TS mirror location).

2. **`web/src/lib/motion.ts`** (new) — TS mirror per brief verbatim:
   ```ts
   export const EASE_HOUSE: [number, number, number, number] = [0.66, 0, 0.2, 1];
   export const D_CAM = 1.4;
   ```

3. **`web/src/journey/Camera.tsx`** — imports `EASE_HOUSE, D_CAM` from `../lib/motion`; `transition={{ duration: 1.4, ease: [0.66, 0, 0.2, 1] }}` → `transition={{ duration: D_CAM, ease: EASE_HOUSE }}`.

4. **`web/test/motion-tokens.test.ts`** (new) — the guard test from the brief, verbatim.

5. **CSS sweep** of `web/src/journey/journey.css` and `web/src/lab/lab.css` — 62 + 19 = 81 lines patched (full ledger below).

## Rule interpretation (some cases weren't in the brief's exception table)

- **R1 (duration)**: mapped every `transition`/one-shot `animation` duration to the nearest tier, including values outside the brief's example list (e.g. `.15s`→quick, `.1s`→quick, `.28s`/`.34s`/`.38s`→quick, `.55s`/`.62s`/`.66s`/`.72s`→soft, `.85s`→scene, `1.5s`→cam — nearest available tier; no higher tier exists above 1.4s).
- **R2 (curve), two independent triggers**, read from the brief's exact wording ("位移/縮放/佈局類 transition 的 ease(未寫)**與**字面 cubic-bezier(.4,0,.2,1)"):
  - (a) *layout-class* transitions (property includes `transform: translate/scale`, or a genuinely layout-shifting property like `padding-right`) whose current easing is the **default `ease`** (written explicitly or omitted) → swap to `var(--ease-house)`.
  - (b) **any** literal `cubic-bezier(.4,0,.2,1)` occurrence, **unconditionally** — this reads as the "generic Material-standard curve to consolidate," confirmed by it appearing identically on `lab-stage`/`sb-stage`/`sb-textview` in the brief's own named-example list (all layout properties), and it's not grammatically scoped to "layout-class" the way clause (a) is. Under this reading I also swept `overlayIn` and `bsDraw`, which use the identical literal but weren't named in the brief's examples — flagged as a judgment call below.
  - Named/custom curves other than plain `ease` or literal `.4,0,.2,1` (e.g. `ease-out`, `ease-in-out`, or any other distinct `cubic-bezier(...)` value) are **never** swapped by the general rule — only duration is mapped. This is why `bornWave`, `shard`, `addCardIn`, `uMeasure`, `ucFly`, `orbitBloom`, `igniteSpine`, `igniteNode`, `usage-entry`'s `bottom` curve, `gather`, `.fill`'s track curve, `burstFlash`/`igniteFlash`/`nascentIgnite` (`ease-out`) all keep their literal curve — matching the brief's protected-curve list, and I extended the same logic to a couple of same-valued-but-unnamed instances (`orbitBloom`, `.fill`) that the brief's example list happened not to spell out.
  - `stroke-dasharray`/`stroke-dashoffset` "line-draw" animations (`draw`, `igniteRib`, `motifLink`) are treated as **not** layout-class (they don't move/scale the element) — a plain `ease` on them stays untouched; only duration maps. `bsDraw` is the one exception: its curve is literally `.4,0,.2,1`, which triggers rule (b) unconditionally regardless of property class.
- `talkIn` in `.talk` (curve `.3,0,.2,1`, not `.4,0,.2,1`) was swept per the brief's **explicit named override**, even though it doesn't match rule (b) by value. The second `talkIn` usage in `.sb-textview` (curve = default `ease`, has `transform`) was independently swept by rule (a).
- `.story.flying`'s `filter .9s ease` sub-transition (duration mapped, curve untouched — filter isn't layout-class) is separate from its `transform 1.15s cubic-bezier(.45,0,.15,1)` sub-transition (both duration and curve kept literal, per the brief's JS-timer + protected-curve exception).
- `bornWave`'s duration (`1.4s`) was swapped to `var(--d-cam)` per the brief's explicit "恰為 --d-cam,可吃 token" note; its curve stayed literal (protected).

## Bug found and fixed during self-review

My first sweep pass (a line-based Python script, chosen over the Edit tool because many lines share identical literal text like `transition:opacity .3s ease}`, which isn't unique enough for Edit's replace) appended exception-rationale text like `(與 hatchTimer 1200ms 對齊)` **outside** the closing `*/` of the exception comment on 5 lines (`.story.flying`, `hatchIn`, `overlayOut`, `readSweep`, `weigh`), producing stray parenthesized text sitting outside any comment/rule — invalid CSS. Caught this by reviewing `git diff` before committing, and fixed all 5 by folding the annotation text inside a single `/* ... */`. Re-verified with `grep -nF '*/(' journey.css lab.css` → 0 matches after the fix, and confirmed `npm run build` (a full `vite build`, which parses/bundles the CSS) succeeds.

## What was tested and results

- TDD RED → GREEN on `web/test/motion-tokens.test.ts` (evidence below).
- Full suite: `cd web && npx vitest run` → **130 passed / 0 failed** (includes `css-keyframes.test.ts`, `reduced-motion.test.ts`, `type-scale.test.ts` — none broken by the sweep).
- `cd web && npm run typecheck` (`tsc --noEmit`) → clean.
- `cd web && npm run build` (`tsc --noEmit && vite build`) → succeeds; CSS bundles without parse errors.
- Confirmed 0 remaining literal `cubic-bezier(.4,0,.2,1)` in either swept file; 0 remaining literal `cubic-bezier(.66,0,.2,1)` (the house curve itself never appears as a literal anywhere, only via the token/import); `var(--ease-house)` appears 6× in each file.
- Brace/paren balance check on both swept files (sanity only): balanced (364/364 braces + 474/474 parens in journey.css; 166/166 + 210/210 in lab.css).

### TDD Evidence

**RED** — before `web/src/lib/motion.ts` existed:
```
$ cd web && npx vitest run test/motion-tokens.test.ts
"message":"Failed to resolve import \"../src/lib/motion\" from \"test/motion-tokens.test.ts\". Does the file exist?"
```
Expected failure: the test imports `EASE_HOUSE`/`D_CAM` from a file that doesn't exist yet.

Intermediate RED (after theme.css + motion.ts + Camera.tsx, before the CSS sweep):
```
$ cd web && npx vitest run test/motion-tokens.test.ts
numPassedTests: 2, numFailedTests: 1
AssertionError: journey/journey.css 沒半處引用 --ease-house?掃描沒做:
  expected '...' to contain 'var(--ease-house)'
```
Expected: token+mirror tests pass; sweep test still red because journey.css/lab.css hadn't been swept yet.

**GREEN** — after the full CSS sweep:
```
$ cd web && npx vitest run
PASS (130) FAIL (0)
```

## Files changed

- `web/src/theme.css` — token block added.
- `web/src/lib/motion.ts` — new, TS mirror.
- `web/src/journey/Camera.tsx` — import + use tokens.
- `web/test/motion-tokens.test.ts` — new guard test (verbatim from brief).
- `web/src/journey/journey.css` — 62 lines swept.
- `web/src/lab/lab.css` — 19 lines swept.

### Full sweep ledger (journey.css, 62 lines)

Swept to token duration only (color/opacity/filter transitions, non-layout, curve untouched):
`.thread`, `.cnode`, `.story` (filter/opacity .8s→scene), `.story .cap`, `.stage-overview .field`, `dropGlow`, `addScrimIn`, `.add-drop`, `.drop-bone`, `.add-go`, `.orbits` (opacity .6s→soft), `.story.flying`'s `filter .9s` sub-transition, `.flying .field .story:not(.flying)`, `.flying .nascent`, `burstFlash`, `shardFade`, `.gest-x`, `umapIn`, `.udot`'s transition (not its `uMeasure` animation), `uFade`×3 (uring/uscar, umap-orbits, udust), `.ubone`, `.uname`, `.uunit`, `.ustar.cold .uname`/`.ucold-note`, `.umap.tight .uname`/`.ucost`, `.usage-entry` color part, `.usage-entry b`, `draw`, `stubIn`×2 (reassemble + ignite), `igniteFlash`, `igniteRib`, `.gest-resume`, `.reanalyze`.

Swept duration + protected-curve preserved (curve stays literal, only the number changed):
`bornWave`(→d-cam, curve `.2,.7,.2,1` kept), `addCardIn`(curve `.22,1,.36,1`), `shard`(curve `.2,.55,.25,1`), `uMeasure`(curve `.2,.7,.2,1`), `ucFly`(curve `.2,.7,.2,1`), `orbitBloom`(curve `.2,.7,.2,1`), `nascentIgnite`(curve `ease-out`), `gather`(curve `.2,.55,.25,1`), `igniteSpine`(curve `.3,0,.2,1`), `igniteNode`(curve `.2,1.5,.4,1`), `usage-entry`'s `bottom` sub-transition(curve `.3,.7,.2,1`).

Swept curve → `var(--ease-house)` (+ duration mapped where not JS-pinned):
`accIn`, `.story.skel-in`(`skelIn`), `.nascent-whisper`, `.umap .ucenter.flyin .uc-halo`(`ucHalo`), `.single-overlay`(`overlayIn`), `.lab-stage`, `.sb-stage`, `.sb-textview`(padding-right transition), `.sb-textview`(`talkIn` usage), `.talk`(`talkIn` usage, named override), `.bonestage .bs-spine`(`bsDraw`, literal `.4,0,.2,1`), `.single-overlay.out`(`overlayOut` — curve swapped, duration kept literal `.46s` per JS-timer pin).

Untouched entirely (infinite loop / natural cycle, exception comment added):
`freshHalo`, `nascentHalo`, `nascentBreath`, `phPulse`, `hy-drip`, `readSweep`, `weigh`, `dormBreath`×2.

Untouched entirely (JS-timer + protected curve both, exception comment added):
`.story.hatching`(`hatchIn` — whole declaration, both duration `1.1s` and curve `.35,0,.15,1` unchanged); `.story.flying`'s `transform 1.15s cubic-bezier(.45,0,.15,1)` sub-transition (comment added inline, only its filter sibling was touched).

### lab.css ledger (19 lines)

Duration-only: `.lab-seg button`/`.lab-slugs button`, `.lab-readout`, `.sb-bar button`, `.src-annot .ann`, `.sb-textview .acc`, `.sb-textview .acc-h`, `.bonestage .motif-occ`.

Duration + protected curve: `.sb-textview .u .fill` (curve `.2,.7,.2,1` kept), `.bonestage .bs-node`(`bsNodeIn`, plain opacity, `ease` kept — no transform, not layout-class).

Duration-only, dashoffset (not layout-class): `.bonestage .motif-link`(`motifLink`).

Curve → `var(--ease-house)`: `.lab-stage`, `.sb-stage`, `.sb-textview`(`talkIn` usage + padding-right), `.talk`(`talkIn`, named override), `.bonestage .bs-spine`(`bsDraw`, literal `.4,0,.2,1`).

Untouched (infinite loop, comment added): `.bonestage .diag-pulse`(`diagPulse`), `.bonestage .thread-flow`(`threadFlow`), `.bonestage .motif-occ.pulse`(`motifPulse`).

## Self-review findings

- Found and fixed the malformed-comment bug described above (5 lines) before committing — caught via `git diff` review, not by the test suite (the guard test only checks token presence/absence, not comment well-formedness).
- Cross-checked exhaustively via `grep -n "transition\|animation"` on both files against my line-by-line plan before writing the sweep script, and again after, to make sure nothing was missed. No leftover un-swept `.4,0,.2,1` literals remain.
- Two judgment calls not explicitly covered by the brief's exception table (documented above): sweeping `overlayIn` and `bsDraw`'s curves (not named in the brief's examples, but matching rule (b)'s literal-value trigger), and treating `orbitBloom`/`.fill` as protected-curve (matching value `.2,.7,.2,1`) rather than swept, for consistency with the brief's stated logic. If the intent was narrower, revisit: `journey.css:239` (`overlayIn`), `lab.css:206` (`bsDraw`), `journey.css:414` (`orbitBloom`, kept), `lab.css:198` (`.fill`, kept).
- No YAGNI violations: did not touch `viz/` (out of scope per task constraints), no speculative config/flexibility added, no unrelated renames/refactors.
- `git status`/`git diff --stat` show exactly 6 files touched, all directly required by the task (4 modified + 2 new).

## Issues or concerns

- The two judgment-call items above (`overlayIn`, `bsDraw` swept; `orbitBloom`, `.fill` kept) are my best-effort extrapolation of the brief's stated rules to instances its example list didn't explicitly name. They're internally consistent with the stated R1/R2 logic and don't fail any existing test, but flagging for awareness in case the original intent was to sweep only the exactly-named examples.
- `1.5s → var(--d-cam)` (`nascentIgnite`) shifts actual duration by −0.1s (~7% faster); this is the correct nearest-tier mapping per R1 but is a small behavior change worth knowing about — it's the ignite/"點火" spark burst on the nascent-star entry, not user-facing-critical timing.

## Verification commands run

```
cd web && npx vitest run                    # 130 passed / 0 failed
cd web && npm run typecheck                 # clean
cd web && npm run build                     # succeeds (tsc + vite build, CSS parses)
```

## Fix: bsDraw curve revert (Task 8 review finding)

Review flagged `web/src/lab/lab.css:206` — the initial sweep tokenized `bsDraw`'s easing
via rule (b) (literal `.4,0,.2,1` → unconditionally swept, per the judgment call documented
above under "Self-review findings"). On reflection that call was wrong: `bsDraw` animates
`stroke-dashoffset` (a line-draw animation, not a layout/scale/translate transition), which
is the same class as `draw`/`igniteRib`/`motifLink` — all three were correctly left with
their literal curve untouched by rule R2 (only their durations were tokenized). `bsDraw`
should follow the same pattern. This is now the single documented exception withdrawn from
this report's ledger: `bsDraw`'s curve moves from "swept" back to "duration-only, curve
protected," matching the ledger category `.bonestage .motif-link`/`draw`/`igniteRib` already sit in.

### Before/after (`web/src/lab/lab.css:206`)

Before:
```css
.bonestage .bs-spine{stroke-dasharray:1;stroke-dashoffset:1;animation:bsDraw var(--d-scene) var(--ease-house) .12s forwards}
```

After:
```css
.bonestage .bs-spine{stroke-dasharray:1;stroke-dashoffset:1;animation:bsDraw var(--d-scene) cubic-bezier(.4,0,.2,1) .12s forwards}
```

Duration stays tokenized (`var(--d-scene)`); easing reverts to the literal curve it held
before the sweep (confirmed via `git show c679dd3^:web/src/lab/lab.css`, which shows the
pre-sweep line as `animation:bsDraw 1s cubic-bezier(.4,0,.2,1) .12s forwards` — duration was
`1s`, now correctly `var(--d-scene)` which equals `.9s`).

### Tests run

- `cd web && npx vitest run test/motion-tokens.test.ts test/css-keyframes.test.ts` → **PASS (4) FAIL (0)**.
  `motion-tokens.test.ts`'s sweep-guard test (`簽名曲線不得以字面量散落...`) still passes:
  lab.css still contains `var(--ease-house)` 5 other places (`.lab-stage`, `.sb-stage`,
  `.sb-textview`×2, `.talk`), so removing the one `bsDraw` occurrence doesn't trip the
  "must contain `var(--ease-house)`" assertion.
- `cd web && npx vitest run` → **PASS (130) FAIL (0)** (full suite, pristine).
- `cd web && npm run typecheck` → clean (`tsc --noEmit`, no output/errors).

### Other files

No other file needed changes. `draw`/`igniteRib`/`motifLink` in `journey.css`/`lab.css` were
already correctly left untouched by the original sweep (verified by re-reading their lines
before editing) — this fix is a single-line, single-file revert exactly as scoped.
