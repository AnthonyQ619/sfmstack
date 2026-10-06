# Campaign: triage-bands-2026-10 — which SceneTriage bands predict a poor delivery

**This is a raw evidence table. Cite it; do not plan from it.** The rules it supports
live in [`plan/scene_to_pipeline.md`](../plan/scene_to_pipeline.md) §2 on reading
`combined_change`, and in [`health/bands.md`](../health/bands.md) on what a band has to
earn to keep its place.

## The question

Three of this module's appearance metrics carried the same `healthy` ceiling of 0.12 —
`combined_change`, `color_shift` and `exposure_shift` — and a census of every stored
reading found most corpus readings above it. A fire rate alone settles nothing:
[`band-calibration-2026-10`](band-calibration-2026-10.md) retired
`illumination_change` at a 79% fire rate **because** its precision was 31% against a
40% base rate, i.e. it fired more often on good deliveries than on poor ones. So the
question for the remaining three is the same one, and it is precision.

## Method

A1's definitions, reused unchanged so the verdicts are comparable: a **poor delivery**
is `auc30 < 0.5`; the ground-truth set is 20 captures of which 8 are poor, a **40% base
rate**; and **every reading counts**, not one per capture.

Two departures, both deliberate:

- **Readings come from the artifact manifests**, not from `chain.json`. This
  repository's authority order puts the manifest first and `chain.json` never, because
  it records only agent-requested steps. 141 readings over the 20 captures.
- **Split by `pairing`, and then by capture family.** The pooled figure can separate
  capture families rather than delivery quality — the families here are not balanced
  between poor and good — so a band only counts as discriminating if it does so
  *within* a family that holds both.

## Pooled, under the default `consecutive` pairing

| metric | readings | fired | precision | base | fires on poor | fires on good |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `combined_change` | 99 | 53% | **75%** | 46% | **87%** | **25%** |
| `color_shift` | 99 | 53% | 67% | 46% | 76% | 32% |
| `exposure_shift` | 99 | 6% | **17%** | 46% | **2%** | 9% |
| `illumination_change` *(A1's control, retired)* | 99 | 67% | 44% | 46% | 63% | 70% |

## Within family, and this is what decides it

Only three families hold both a poor and a good delivery, so only three can be read.

| family | `combined_change` | | | `color_shift` | | |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| | precision | poor | good | precision | poor | good |
| ETH (base 58%) | **90%** | 60% | **9%** | 60% | 100% | **91%** |
| EuRoC (base 29%) | **58%** | **100%** | 29% | *never fires* | — | — |
| TUM-VI (base 33%) | **100%** | 100% | **0%** | *never fires* | — | — |

- **`combined_change` discriminates within every family that can be read**, three of
  three, each well above its family's base rate. It is not a family artifact.
- **`color_shift` does not survive the same test.** Its pooled lead over the base rate
  was a family artifact: inside ETH it fires on 100% of poor readings *and* 91% of good
  ones, and in the other two families it never fires at all.
- **`exposure_shift` is anti-correlated.** It fires on 2% of poor readings and 9% of
  good ones, at 17% precision against a 46% base. A band that fires almost only on good
  deliveries is worse than a quiet one.

## Under `pairing: all`, the discrimination collapses

| metric | fired | precision | base |
| --- | ---: | ---: | ---: |
| `combined_change` | 90% | 39% | 36% |
| `color_shift` | 76% | 44% | 36% |

Firing on nearly everything drives precision to the base rate. The band is an alarm
under adjacent pairing and nothing but noise under full pairing.

## What this settles

- **`combined_change` keeps its 0.12 ceiling**, and the ceiling sitting below the
  population median is **why** it works: 87% of poor readings caught at a 25%
  false-alarm rate, under the default pairing. A census finding that the population
  exceeds the ceiling is not grounds to raise it — raising it would remove the
  discrimination.
- **`color_shift`'s band is retired** on the same evidence standard that retired
  `illumination_change`.
- **`exposure_shift`'s band is retired**, for firing on the wrong class.
- **Read `combined_change` only against adjacent pairing.** Under full pairing it
  carries no signal.

## What this does not settle

- The three families that hold only one class — a studio-rig set with no poor delivery
  and a handheld set with no good one — cannot be read either way.
- Whether a ceiling other than 0.12 would discriminate better. Only the shipped value
  was tested.
- The band's documented basis. Re-measuring the ten scenes it was fitted on did not
  reproduce the range recorded for it, which is a provenance defect noted in
  `sources.md` and independent of the precision measured here.
