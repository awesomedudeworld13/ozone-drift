# ozone-drift

**Does a benchmark score overstate operational skill when the distribution
shift is ordinary and physical, rather than adversarial or artifactual?**

**Answer: no — once the split is honest, it doesn't overstate at all.** Which is
the most useful result this domain could have produced.

---

## Result

Houston–Galveston–Brazoria airshed, 17 monitoring sites pooled, 49,882 site-days,
1,008 exceedance days. Benchmark era 2015–2019, operational era 2022–2025.
Date-clustered bootstrap, thresholds frozen on validation.

| cell | what changes | TSS (core) | TSS (extended) |
|---|---|---|---|
| 1 · benchmark era, **random split** | the protocol most published air-quality ML uses | **0.808** | 0.665 |
| 2 · benchmark era, **chronological split** | earlier days train, later days test | **0.593** | 0.500 |
| 3 · **operational era**, cell-2 model frozen | deployment reality, 2022–2025 | **0.670** | 0.602 |

| step | ΔTSS (core) | ΔTSS (extended) |
|---|---|---|
| temporal leakage (cell 1 → 2) | **+0.215** | +0.164 |
| operational drift (cell 2 → 3) | **−0.077** | −0.101 |
| total | +0.138 | +0.063 |

**Essentially the entire apparent gap is the random split, not drift.** Shuffling
a pooled time series overstates skill by 0.215 TSS — a model can interpolate
tomorrow from autocorrelated neighbouring days, and can see the same regional
ozone episode at other sites in its training set. Remove that, and the model
scores *better* on 2022–2025 than on its own held-out 2019 test.

That negative drift is the control result the multi-domain study needed: where
the shift is seasonal and physical, with no adversary and no dataset-construction
artifact, a benchmark score survives deployment.

## Does training on operational data close the gap?

**No — at the core tier it measurably made things worse.**

| training source | benchmark test | operational test |
|---|---|---|
| benchmark-trained (2015–2019) | 0.593 | **0.637** |
| operational-trained (2022–2025) | 0.539 | **0.501** |

On identical operational test rows: **−0.136, 95% CI [−0.255, −0.009]**. The
interval excludes zero *below*. At the extended tier the direction is the same
(−0.154) but the interval includes zero, so nothing is claimed there.

This matches the sibling solar project's finding that live training does not
close the gap. Caveat stated plainly: the operational era supplies fewer training
days, so part of this may be sample size rather than era — separating those needs
a dose-response curve, which this domain does not yet run.

## The model is doing real work

Persistence ("tomorrow looks like today") scores TSS **0.257** on the operational
era against the model's **0.670**. Every operational forecasting domain has a
trivial baseline that is embarrassingly hard to beat; reporting it is the same
discipline as reporting that a regex beats published models on a phishing
benchmark. Top features: previous-day ozone, day-of-year, wind direction,
maximum temperature — physically sensible, not artifacts.

## Both feature tiers, both reported

| tier | variables | rows | sites | exceedances | base rate |
|---|---|---|---|---|---|
| core | temperature, wind speed & direction, previous-day ozone, calendar | 49,882 | 17 | 1,008 | 0.0202 |
| extended | + relative humidity, dew point | 21,350 | 7 | 488 | 0.0229 |

Humidity is reported at only ~34% of site-days, so requiring it costs 57% of rows
and 10 of 17 sites. Both tiers are pre-registered and both are reported —
selecting one after seeing which gave a larger gap would be exactly the effect
this project exists to criticise.

## Pre-registered predictions

Five were committed before any modelling. **One failed, one is inconclusive**, and
both are recorded as such in [PREREGISTRATION.md](PREREGISTRATION.md):

| | prediction | observed | verdict |
|---|---|---|---|
| O1 | base rate 4–15% | 0.0202 | **FAILED** |
| O2 | leakage step 0.02–0.25 | +0.215 | HELD |
| O3 | operational gap < 0.15 | −0.077 | HELD |
| O4 | ozone < solar < storms < phishing | partial | **PARTIAL** |
| O5 | F1 point degrades more than TSS | neither degraded | **INCONCLUSIVE** |

O1's failure matters: exceedance is rarer than anticipated (2016 ran at 0.62%),
so accuracy is even more useless here than assumed. An unpredicted effect did
appear — at the leakage step the F1 operating point is damaged roughly twice as
much as the TSS point (+0.430 vs +0.215) — and is flagged as found, not
predicted.

---

## Why this domain exists in the study

This is the third domain in a multi-domain investigation of the gap between what
a machine-learning benchmark reports and what a model does once deployed. Each
domain is chosen for a **different kind of distribution shift**, because the
interesting question is not *"do benchmarks overstate?"* — one domain can answer
that — but *"what predicts how badly?"*

| Domain | Kind of shift | Result |
|---|---|---|
| [Solar flares](https://github.com/awesomedudeworld13/SolarFlarePredictor) | natural temporal + solar-cycle boundary | gap +0.078 TSS |
| Geomagnetic storms *(same repo)* | natural temporal | gap +0.165 TSS |
| [Phishing URLs](https://github.com/awesomedudeworld13/phish-drift) | adversarial + dataset construction | gap +0.508 to +0.996 TSS |
| **Ozone exceedance** *(this repo)* | **seasonal / physical** | **+0.138 total, −0.077 drift** |

Ozone's job in the study is to be the **control**. Its shift is the mildest and
most benign kind there is: the atmosphere in 2026 obeys the same chemistry it
obeyed in 2016, nobody is adapting to evade the forecast, and the measurement
network is stable and publicly documented. If a substantial gap appears even
here, the effect is close to universal. If the gap is small, that is the more
valuable result — it identifies the conditions under which a benchmark score
*can* be trusted, which no single collapsing domain can establish.

A null result here is therefore a finding, not a failure, and will be reported
as one.

## The task

> P(tomorrow's maximum 8-hour ozone concentration exceeds the NAAQS standard of
> 70 ppb) at any monitoring site in the Houston–Galveston–Brazoria airshed.

Originally specified as a *single fixed station*. The feature-computability
spike showed that is not viable — the best-instrumented site recorded **zero**
exceedance days in 2016, and TSS is undefined on a year with no events. The unit
is now the pooled airshed; see [SPIKE.md](SPIKE.md).

Measured base rate is **2.0%** across 2015–2025, lower than the 4–15% predicted
in O1 (recorded as FAILED). Rarer than expected, which only sharpens the point
that accuracy is useless here: a model predicting "no exceedance" every day
scores 98% accuracy with zero skill.

## Protocol

The decomposition is carried over from `phish-drift`, minus the cell that does
not apply:

| Cell | Corpus | Isolates |
|---|---|---|
| 1 | Historical EPA AQS, random i.i.d. split | the protocol most papers use |
| 2 | Historical EPA AQS, **chronological** split | temporal leakage from shuffling a time series |
| 3 | Live/recent observations, model frozen from cell 2 | genuine operational drift |

Cell 2 replaces phish-drift's domain-disjoint split. The leakage mechanism in a
time series is different: randomly shuffling days puts tomorrow in the training
set and yesterday in the test set, and adjacent days are strongly autocorrelated,
so a random split lets the model interpolate rather than forecast. Splitting
chronologically — train on earlier years, test on later ones — is the honest
protocol and the difference between the two is the quantity of interest.

Carried over unchanged from the sibling projects:

- **One feature function** for historical and live data, no vocabulary fitted on
  training data.
- **Thresholds frozen on a validation split**, at F1 and TSS objectives, never
  selected on the data being scored.
- **TSS as the headline**, accuracy reported only to show its inadequacy at a
  low base rate.
- **Block bootstrap for confidence intervals.** Consecutive days are correlated
  — an ozone episode lasts several days — so i.i.d. resampling of days would
  make intervals far too narrow. This is the time-series analogue of clustering
  on active regions (solar) or registrable domains (phishing); the block length
  must be at least the typical episode duration.

## Features

Meteorological predictors available at forecast time, from the previous day and
the current morning. Nothing that would not be available operationally:

temperature (max, morning), wind speed and direction, relative humidity,
solar radiation, barometric pressure, mixing height where available, previous
day's ozone maximum, day of year and day of week (weekday traffic patterns
matter for the precursor load).

## Data sources

| | |
|---|---|
| Historical ozone + meteorology | [EPA Air Quality System (AQS)](https://aqs.epa.gov/aqsweb/documents/data_api.html) — free API key, bulk download available |
| Recent/live observations | [OpenAQ](https://openaq.org/) or [EPA AirNow](https://docs.airnowapi.org/) — free keys |
| Exceedance standard | NAAQS 8-hour ozone, 70 ppb (2015 standard) |

## Why this repository can wait

Unlike the phishing feeds — OpenPhish rotates a 300-URL window and discards
what falls out, so a day not collected is gone permanently — **EPA and OpenAQ
observations are archived and retrievable retroactively**. Any date range can be
back-fetched later with identical results. There is consequently no collection
clock running on this domain, which is why the sibling phishing project was
built first.

The one thing that does need to happen early is the **feature-computability
check**: confirming that every predictor used on the historical corpus can be
computed identically from the live API. That is the go/no-go for the whole
domain and should not be discovered in January.

## Layout

```
ozonedrift/
  aqs.py          EPA AQS loading, forecast-time feature construction
  splits.py       random vs chronological partitions, the era gate
  model.py        training, threshold freezing, the persistence baseline
  evaluate.py     TSS, Brier, date-clustered bootstrap  (SHARED — see below)
  gap.py          the three cells, the attribution, and the 2x2
  cli.py          fetch / survey / report
tests/            protocol invariants, run on every push
```

### Reproducing

```bash
pip install -r requirements.txt
python -m ozonedrift.cli fetch      # ~150 MB of EPA annual files, cached
python -m ozonedrift.cli survey     # per-year coverage and the era gate
python -m ozonedrift.cli report     # three cells + the 2x2 -> RESULTS.md
python tests/test_protocol.py       # the invariants the study depends on
```

`RESULTS.md` is generated, never hand-edited.

### The shared harness

`ozonedrift/evaluate.py` is **byte-identical** to `phishdrift/evaluate.py` apart
from a provenance docstring. It is duplicated rather than imported so neither
repository needs the other installed — but that trade has a cost worth naming:
if the copies drift, the cross-domain comparison silently stops being a
comparison. The whole multi-domain claim depends on every domain's TSS being the
same quantity computed the same way.

`tests/test_protocol.py` pins the hash of the shared code section, so a local
edit fails CI. It cannot detect upstream drift. **When a third domain needs it,
extract it into a package all three depend on rather than making a third copy** —
that extraction is the software deliverable the multi-domain design implies, and
it should be driven by real needs rather than guessed at in advance.
