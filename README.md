# ozone-drift

**Does a benchmark score overstate operational skill when the distribution
shift is ordinary and physical, rather than adversarial or artifactual?**

Status: **design committed, implementation pending.** This repository holds the
protocol. Nothing has been fitted or scored yet, and that is deliberate — the
design is being written down before any modelling so the predictions in
`PREREGISTRATION.md` are falsifiable.

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
| [Phishing URLs](https://github.com/awesomedudeworld13/phish-drift) | adversarial + dataset construction | gap +0.996 TSS (total collapse) |
| **Ozone exceedance** *(this repo)* | **seasonal / physical** | *pending* |

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
> 70 ppb) at a fixed monitoring station in the Houston–Galveston–Brazoria area.

Houston has among the worst ground-level ozone in the United States, with
roughly 20–40 exceedance days per year. That yields a base rate near 8% — low
enough that the threshold-objective effect documented in the sibling projects
should be observable, and low enough that accuracy is a useless metric, which is
itself worth demonstrating on a third independent domain.

## Protocol

The four-cell decomposition is carried over from `phish-drift`, minus the cell
that does not apply:

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

## Planned features

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

## Planned layout

```
ozonedrift/
  features.py     meteorological predictors; one contract for both corpora
  aqs.py          EPA AQS historical loading, the two splits
  collect.py      recent observations via OpenAQ/AirNow
  model.py        training, threshold freezing
  evaluate.py     TSS, Brier, block bootstrap
  gap.py          the three cells and the attribution
```

`evaluate.py` and much of `gap.py` are near-identical to their counterparts in
`phish-drift`; the intention is to lift them across rather than rewrite them,
and if that turns out to require more than mechanical changes, the shared
harness should be factored into a small package both repositories depend on.
That refactor is the software deliverable the multi-domain design implies, and
it should be driven by the second domain's real needs rather than guessed at in
advance.
