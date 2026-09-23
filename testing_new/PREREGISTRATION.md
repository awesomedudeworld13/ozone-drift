# Pre-registration: testing-new (dose-response, more history, live forecasts)

**Committed on 2026-09-22 (CDT) BEFORE any model below was trained and before
the live forecaster ran.** EPA files for 2005–2014 and 2026 were downloading
at commit time; no feature frame from them had been built. This adds to
`PREREGISTRATION.md` on main and does not replace it. Nothing below may be
edited after the first score exists; corrections go in "Deviations".

## Why

Main's RQ2 result was that training on the newer era **hurt**: D − B = −0.136
(95% CI −0.255 to −0.009, core tier). Main's own caveat: the newer-era model
trained on ~2.8 years (2022-01-01 to 2024-10-17), the older one on 3.5, so
"era" and "amount of data" are confounded. This design separates them, adds
history back to 2005, tests a stronger learner and one regional feature, and
starts a genuinely live forecast record.

## Fixed windows (identical for every arm)

- **Test:** 2025-05-25 to 2025-12-30. Main's D-cell test days, both tiers.
- **Validation (common):** 2024-10-18 to 2025-05-24. Every arm picks its
  TSS/F1 thresholds here, so arms differ **only** in their training data.
  (Main's cell B picked its threshold on benchmark-era validation, so the
  bm5 arm below is not numerically identical to main's B. That's expected.)
- Both feature tiers (core, extended) for every retrospective result, as main's
  addendum requires. The live forecast is core tier only (see L1).
- Scoring: main's `gap.evaluate_cell` (date-clustered bootstrap, 1,000
  resamples) and `benchgap.evaluate.paired_difference_ci` for differences.
  Label, features, consecutive-day gate: main's `aqs.build_features`, unchanged.

## Training arms (RandomForest, main's `model.train` recipe)

| arm | training days |
|---|---|
| op1 | 2023-10-18 to 2024-10-17 (1 yr, newer era) |
| op2 | 2022-10-18 to 2024-10-17 (2 yr) |
| op28 | 2022-01-01 to 2024-10-17 (2.8 yr, main's D span) |
| bm3 | 2017-01-01 to 2019-12-31 (3 yr, older era) |
| bm5 | 2015-01-01 to 2019-12-31 (main's benchmark era) |
| bm_op | bm5 + op28 |
| hist_bm | 2005-01-01 to 2019-12-31 |
| hist_bm_op | hist_bm + op28 |

2020–2021 stay excluded, as on main.

## Hypotheses (core tier primary; extended reported alongside)

- **Z1 (primary): at equal size, era doesn't hurt.** TSS(op28) − TSS(bm3), paired
  on the test rows. *Predicted:* within ±0.10 with the CI including 0. If the CI
  excludes 0 below, the newer era really is harder to learn from, and main's
  "hurt" stands as an era effect.
- **Z2: more newer-era data helps.** TSS(op28) − TSS(op1) > 0. *Predicted:*
  +0.02 to +0.15.
- **Z3: combining eras beats either alone.** TSS(bm_op) − TSS(bm5) > 0 with the
  CI excluding 0. *Predicted:* +0.02 to +0.10.
- **Z4: more history helps a little.** TSS(hist_bm_op) − TSS(bm_op).
  *Predicted:* 0.00 to +0.05. The CI is expected to include 0.
- **Z5: the model beats persistence.** The final dev model's (below) test TSS at
  its frozen threshold exceeds the persistence baseline's TSS at persistence's
  own validation-chosen threshold, on the same rows.

## Stronger learner and regional feature (reported side by side)

On the hist_bm_op training days, four variants: {RF, HGB} × {base features,
+ `airshed_o3_max`}. `airshed_o3_max` is the highest `o3_max8h` among all HGB
sites on day D, computed from all sites that reported that day. HGB:
`HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05,
class_weight="balanced", random_state=20260920)`.

**Selection rule for the final model F (fixed now):** the variant with the
highest core-tier TSS on the **common validation window** is the dev winner.
All four are then scored on the test window and reported, whichever wins. **F**
is the winner's recipe refit on 2005–2019 + 2022-01-01 to 2026-03-31 (the full
published AQS record), keeping the dev winner's frozen thresholds.

## Live forecast (P-live)

A daily GitHub Actions job on the branch reads AirNow's **keyless** hourly files
(`files.airnowtech.org/airnow/YYYY/YYYYMMDD/HourlyData_YYYYMMDDHH.dat`) for
the HGB-county AQS IDs. It rebuilds day D's core features the way AQS daily
summaries do:
- **Temperature:** daily mean and max, °C converted to °F.
- **Wind:** resultant speed (knots) and direction, daily mean and max.
- **Ozone:** the daily max of 8-hour running averages starting 00–23 LST, with
  at least 6 of 8 hours present.
- **Calendar:** the same features as main.

Local standard time is UTC−6, like AQS "Date Local". The job logs P(exceedance
on D+1) per site from **F** and from **main's benchmark-trained model**
(main's cell-2 recipe, 2015–2019, retrained deterministically). The next day it
verifies each forecast against AirNow-derived `o3_max8h` > 70 ppb.
Record: `testing_new/live_forecasts.csv`.

- **L1.** At the 30-day (2026-10-23) and 60-day (2026-11-22) checks: F − main
  in Brier score and TSS, paired, date-clustered.
- **Honest power statement:** the Houston ozone season is ending. We expect
  only a handful of exceedance site-days by November, possibly zero, so L1 is
  expected to be **inconclusive**. The live record's value is in:
  1. showing the pipeline works end to end in real time
  2. building the record through the 2027 season
  3. measuring AirNow-vs-AQS feature drift once EPA publishes the same days
     (the same preliminary-vs-final question as solar's NRT vs definitive).
- **The extended tier isn't live:** AirNow has no dew point, and deriving it
  from T/RH would break main's frozen decision 5 (identical feature code on
  both sides).

## Reporting

Every arm, variant and tier is reported, including results that contradict a
prediction, in `testing_new/RESULTS.md`.

## Deviations

(none yet)
