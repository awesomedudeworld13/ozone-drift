# testing-new: results (scored once, 2026-09-23 UTC)

From `python -m ozonedrift.dose`; raw numbers in `dose_results.json`. Design
in `PREREGISTRATION.md` (committed first). Every arm is scored on the same test
days (2025-05-25 to 2025-12-30) with thresholds from the same validation
window (2024-10-18 to 2025-05-24). Core tier: 3,656 test site-days, 113
exceedances. TSS at the frozen threshold, date-clustered 95% CI.

## Training arms (RandomForest, core tier)

| arm | training | rows | TSS (95% CI) | peak TSS |
|---|---|---|---|---|
| op1 | newest 1 yr | 6,019 | **0.600** (0.534–0.660) | 0.677 |
| op2 | newest 2 yr | 10,231 | 0.594 (0.492–0.684) | **0.711** |
| op28 | 2.8 yr (main's D) | 14,819 | 0.501 (0.432–0.566) | 0.677 |
| bm3 | 2017–19 | 16,491 | 0.485 (0.419–0.545) | 0.647 |
| bm5 | 2015–19 (main's era) | 27,810 | 0.556 (0.483–0.620) | 0.655 |
| bm_op | bm5 + op28 | 42,629 | 0.448 (0.390–0.503) | 0.663 |
| hist_bm | 2005–19 | 83,189 | 0.496 (0.441–0.550) | 0.680 |
| hist_bm_op | 2005–19 + op28 | 98,008 | 0.449 (0.388–0.503) | 0.686 |

## Verdicts

| | Result (core) | Predicted | Verdict | Extended tier |
|---|---|---|---|---|
| **Z1 (primary)** op28 − bm3 | +0.016 (−0.075 to +0.107) | within ±0.10, CI incl. 0 | **Held** | −0.047 (−0.186 to +0.097), held |
| Z2 op28 − op1 | **−0.099 (−0.188 to −0.009)** | +0.02 to +0.15 | **Failed, reversed** | −0.232 (−0.342 to −0.136) |
| Z3 bm_op − bm5 | **−0.108 (−0.195 to −0.021)** | +0.02 to +0.10 | **Failed, reversed** | −0.024, inconclusive |
| Z4 hist_bm_op − bm_op | +0.001 (−0.079 to +0.087) | 0 to +0.05 | Held | −0.011, inconclusive |
| Z5 dev winner − persistence | −0.046 (−0.166 to +0.076) | > 0 | **Failed** (inconclusive) | +0.005, inconclusive |

**What this says about main's "operational training hurt" result:** at equal
training size, the newer era is no worse to learn from (Z1). So main's
−0.136 was not an era effect.

The surprise is that **more data made the frozen-threshold score worse, not
better** (Z2, Z3). The best arm is the smallest, most recent one: op1, the
single year right before the test. Adding older years, whether newer-era or
older-era, lowered TSS at the frozen threshold.

The threshold-free column (peak TSS) is much flatter: 0.65–0.71 across arms,
with more and newer data slightly ahead. So most of the spread is **threshold
transfer, not ranking skill**. Each arm's threshold is picked on a validation
window that is mostly off-season (Oct–May, few exceedances) and then applied
to a summer-to-winter test. Models trained on different mixes of years produce
probability scales that transfer differently across that seasonal jump.

This is the same lesson the solar branch found: a threshold fitted in one
regime doesn't carry over. It's a design weakness of this pre-registration
(and of main's), reported rather than fixed after the fact.

## Learner and regional feature (hist_bm_op days)

| variant | validation TSS | test TSS (95% CI) |
|---|---|---|
| RF, base | 0.627 | 0.449 (0.388–0.503) |
| RF, + airshed max | 0.685 | 0.517 (0.423–0.595) |
| **HGB, base** (dev winner) | **0.761** | **0.566 (0.487–0.635)** |
| HGB, + airshed max | 0.735 | 0.513 (0.456–0.573) |

- Gradient boosting beats the RandomForest on the same data (+0.12 at the
  frozen threshold).
- The regional feature helps the RF but not HGB.
- **Persistence** (tomorrow = today, threshold chosen on the same validation)
  scores 0.612 on the test: no model variant clearly beats it (Z5).

## Final model F (live)

HGB, base features, refit on 2005–2019 + 2022-01-01 to 2026-03-31 (106,356
site-days), with the dev winner's frozen threshold (TSS point 0.121). The
live forecaster logs F next to main's benchmark-trained RF every day from
AirNow's keyless files (`live_forecasts.csv`).

## What to do with this (next pre-registration, not now)

1. Choose thresholds on an **in-season** validation window, or use a
   probability scale that doesn't need one (report Brier alongside TSS).
2. Weight or window training toward recent years: op1's lead suggests
   recency matters more than volume for this airshed.
3. Treat persistence as the bar to beat. On this test nothing clearly
   clears it, which is itself a finding for the "benchmark vs reality" paper.
