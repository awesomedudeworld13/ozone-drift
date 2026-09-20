# Pre-registration — ozone-drift

Written **before any data was fetched or any model fitted**. Registered
2026-09-20.

This domain's role in the multi-domain study is to be the control: the mildest,
most physical kind of distribution shift available. A small gap here is a more
useful result than a large one, because it would establish the conditions under
which a benchmark score *can* be trusted. Both outcomes are reported.

---

## Research question

When the distribution shift between a benchmark and operation is ordinary and
physical — seasonal, non-adversarial, with a stable measurement network and no
dataset-construction artifact — does a benchmark score still overstate
operational skill, and by how much relative to the adversarial and artifactual
domains already measured?

## Task

P(maximum 8-hour ozone concentration exceeds 70 ppb tomorrow) at a fixed
Houston-area EPA monitoring station.

## Frozen decisions

1. **The station and the historical span are chosen before any modelling**, on
   data-availability grounds only (longest continuous record with co-located
   meteorology), and recorded here once selected. They are not chosen by
   inspecting which station produces a larger gap.
2. **Thresholds are selected on a validation split and frozen**, at F1 and TSS
   objectives. Live data is never used to select a threshold.
3. **Confidence intervals use a moving-block bootstrap**, block length ≥ the
   typical ozone-episode duration (to be set from the autocorrelation function
   of the historical series, before scoring). Daily i.i.d. resampling is
   invalid here and will not be used.
4. **TSS is the headline metric.** Accuracy is reported only to demonstrate its
   inadequacy at this base rate.
5. **Features must be computable identically** from the historical AQS record
   and from the live OpenAQ/AirNow API, using one function. Any predictor that
   fails this check is dropped from both sides, not imputed on one.
6. **Only predictors available at forecast time** are used. No same-day ozone
   maximum, no future meteorology.

## Hypotheses

**O1 — Base rate.** The exceedance base rate at the selected station will fall
between **4% and 15%** over the historical span.

**O2 — Temporal leakage is real but modest.** Moving from a random i.i.d. split
to a chronological split will reduce benchmark TSS by **more than 0.02 and less
than 0.25**. Reasoning: adjacent days are strongly autocorrelated, so a random
split permits interpolation rather than forecasting, but ozone chemistry is
stationary enough that the model is not merely memorising.

**O3 — The operational gap is small.** The chronologically-split model scored on
recent held-out years will lose **less than 0.15 TSS** relative to its
chronological benchmark score. This is the control prediction: with no adversary
and no construction artifact, most skill should transfer.

**O4 — Ordering across domains.** The total benchmark-to-operational gap will
rank: **ozone < solar flares < geomagnetic storms < phishing**. This is the
study's central claim — that the *kind* of distribution shift predicts the size
of the gap — and it is the prediction most likely to fail.

**O5 — The threshold-objective effect reproduces.** The F1-objective operating
point will lose more TSS between the benchmark and operational cells than the
TSS-objective point does, as observed in the solar domain.

## What would falsify the thesis

- If O3 fails and ozone shows a gap above 0.15, then large gaps are not specific
  to adversarial or artifactual domains and the "kind of shift predicts the gap"
  framing is wrong.
- If O4 fails — particularly if ozone's gap exceeds solar's — the ordering claim
  collapses and the multi-domain design yields a weaker result: that benchmarks
  overstate in varied domains, without a predictive account of when.
- If O2 shows a gap near zero, chronological splitting does not matter for this
  task and that specific methodological recommendation does not generalise from
  the sibling projects.

## Reporting commitment

Every cell that can be computed is reported, including nulls and results that
contradict the hypotheses above. Failed hypotheses remain in this file marked
FAILED rather than being removed or rewritten. If additional stations or spans
are examined, all of them are reported, not only those showing an effect.

---

## Verdicts

*Pending implementation. Empty means not yet run, not omitted.*

| Hypothesis | Predicted | Observed | Verdict |
|---|---|---|---|
| O1 base rate in 4–15% | 0.04–0.15 | 0.0420 (pooled, 2023) | **HELD** — but see addendum |
| O2 leakage step in 0.02–0.25 | modest | _pending_ | _pending_ |
| O3 operational gap < 0.15 | small | _pending_ | _pending_ |
| O4 ozone < solar < storms < phishing | ordering | _pending_ | _pending_ |
| O5 F1 point degrades more than TSS point | yes | _pending_ | _pending_ |

---

# Addendum — 2026-09-20: what the feature-computability spike changed

An addition, not a revision. Nothing above is edited. Full detail in
[SPIKE.md](SPIKE.md); this records only the changes to *frozen decisions*.

The spike ran before any model was fitted, and it invalidated the unit of
analysis the original protocol assumed.

## Amended: the unit is the airshed, not a station

Frozen decision 1 named "a fixed Houston-area EPA monitoring station". That is
not viable. At the best candidate station — Park Place (48-201-0416), the only
site with a complete record across all four variables — **2016 contains zero
exceedance days**, and other years carry only 5–18. TSS is undefined on a year
with no events, and at that count no interval could distinguish anything.

The unit of analysis is therefore the **Houston–Galveston–Brazoria airshed**:
all 20 ozone sites across Harris, Brazoria, Chambers, Galveston, Montgomery and
Waller counties, pooled. 2023 yields 4,426 usable site-days and 186 exceedance
days at the core feature tier.

**This is a change of design, not of prediction.** O1 predicted a 4–15% base
rate "at the selected station"; the pooled airshed rate is 0.0420, inside the
band, so the number holds — but it is measured against a design the spike
forced us to change, and it would have *failed* at single-station level in at
least one year (2016, 0.000). It is marked HELD with that caveat rather than
claimed as a clean hit.

## New frozen decision: clustering on date

Pooled site-days are not independent. Ozone episodes are regional, so on an
exceedance day many sites exceed together. Resampling site-days i.i.d. would
count one weather event as twenty observations and make every confidence
interval far too narrow.

**Confidence intervals cluster on DATE.** This is the same dependency structure
the sibling projects already handle — active regions in solar, registrable
domains in phishing — appearing a third time in a third domain. The moving-block
bootstrap over consecutive days (frozen decision 3) is retained *in addition*:
the two address different dependencies (within-day across sites, and
across-day autocorrelation), and both are required.

## New frozen decision: two feature tiers, both reported

Relative humidity and dew point are reported at only ~34% of Houston site-days.
Requiring them costs 57% of rows and 10 of 17 sites.

- **core** — temperature, wind speed, wind direction, previous-day ozone,
  calendar: 4,426 rows, 17 sites, base rate 0.0420
- **extended** — adds relative humidity and dew point: 1,884 rows, 7 sites,
  base rate 0.0430

**Both tiers are reported for every result.** Choosing one after seeing which
produced a larger gap would be the exact selection effect this project exists to
criticise. The near-identical base rates (0.0420 vs 0.0430) indicate the
humidity-reporting subset is not systematically easier or harder on the label.

## New frozen decision: consecutive-day gate

A row is kept only when its successor is literally the next calendar day.
Shifting by one *row* rather than one *day* would turn a record gap into a
multi-day-ahead forecast wearing a one-day-ahead label. Drops 65 rows on 2023.

## New frozen decision: era gate

Benchmark and operational eras are fixed before modelling, subject to a
data-quality gate: **no era may contain a year with zero pooled exceedances.**
This is a property of the data, checkable before any model exists — analogous to
phish-drift's fail-closed label gate — and not a result-dependent choice.

## Recorded limitation: the operational end lags

EPA's bulk files are published through 2026-03-31, roughly six months behind.
The operational sample cannot be genuinely real-time through this source.

Judged acceptable for this domain and stated rather than worked around: the
shift here is seasonal and physical, with no adversary adapting to the forecast,
so a months-old operational sample remains a fair test of deployment-era
performance. What the design requires is that operational years fall *after* the
benchmark era and are processed as raw data rather than a curated extract — both
of which hold. AirNow and OpenAQ offer genuinely recent data but require API
keys, which is why neither backs the reproducible core.
