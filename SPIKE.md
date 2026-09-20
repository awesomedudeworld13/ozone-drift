# Feature-computability spike — 2026-09-20

**Verdict: GO.** Every predictor is computable from a no-authentication public
source, meteorology is co-located with the ozone monitors, and the pipeline runs
end to end. The domain is viable.

The spike's value was not the green light, though — it was four problems found
before any modelling, three of which would have invalidated the design if
discovered later.

---

## What was verified

| Question | Answer |
|---|---|
| Data reachable without an API key? | **Yes.** EPA's pre-generated annual files at `aqs.epa.gov/aqsweb/airdata/` need no registration, unlike the AQS REST API. ~4 MB per pollutant-year. |
| Is the NAAQS target directly available? | **Yes.** `1st Max Value` on the `8-HR RUN AVG BEGIN HOUR` rows is the daily maximum 8-hour ozone — the exact quantity the 0.070 ppm standard is written against. No reconstruction needed. |
| Is meteorology co-located with ozone? | **Yes**, by site number, so an exact join works — no nearest-neighbour matching and no distance-dependent error. 18/20 Houston sites have temperature, 17/20 wind, 7/20 humidity. |
| Does the pipeline run end to end? | **Yes.** 2023 Houston airshed, core tier: 4,426 site-days, 17 sites, 186 exceedance days, base rate **4.2%**. |
| How current is the "operational" end? | Published through **2026-03-31** — the bulk files lag roughly six months. |

## Problem 1 — a single monitoring station is not viable

The original protocol named "a fixed monitoring station". Measured at the best
candidate (Park Place, 48-201-0416, the only site with all four variables and
a complete record):

| year | days | exceedances | rate |
|---|---|---|---|
| 2016 | 360 | **0** | 0.000 |
| 2019 | 360 | 5 | 0.014 |
| 2023 | 363 | 18 | 0.050 |
| 2024 | 355 | 13 | 0.037 |

**2016 has zero positive days.** TSS is undefined on a year with no events, and
5–18 positives per year gives confidence intervals too wide to distinguish
anything. A single station cannot support this study.

**Fix:** pool the whole Houston–Galveston–Brazoria airshed (20 ozone sites).
That yields ~4,400 usable site-days and ~186 positives per year at the core
tier.

**Consequence, and it is not optional:** pooled site-days are *not* independent.
An ozone episode is regional — on an exceedance day, many sites exceed together.
Resampling site-days i.i.d. would treat one weather event as twenty
observations and make every interval far too narrow. **The bootstrap must
cluster on DATE**, exactly as the solar project clusters on active region and
phish-drift on registrable domain. Same failure mode, third domain.

## Problem 2 — humidity costs three quarters of the data

Relative humidity and dew point are genuinely informative for ozone chemistry,
but they are reported at only ~34% of Houston site-days, against ~63% for wind
and ~87% for temperature.

| tier | variables | rows | sites | positives | base rate |
|---|---|---|---|---|---|
| **core** | temperature, wind speed, wind direction | 4,426 | 17 | 186 | 0.0420 |
| **extended** | + relative humidity, dew point | 1,884 | 7 | 81 | 0.0430 |

Requiring humidity costs 57% of rows and 10 of 17 sites.

**Fix:** run both tiers and report both, rather than silently choosing whichever
produces the more interesting gap. The choice is pre-registered, not made after
seeing results.

**Reassuring:** the two tiers have almost identical base rates (0.0420 vs
0.0430), so the humidity-reporting subset is not systematically cleaner or
dirtier on the label. The tier changes sample size, not the task's difficulty.

## Problem 3 — record gaps would silently become easier forecasts

The label is "does tomorrow exceed". Naively shifting by one row within a site
makes a row whose successor is 3 days later into a *three-day-ahead* forecast
wearing a one-day-ahead label — a different, and in some respects easier, task
scored as if it were the stated one.

**Fix:** `build_features` keeps a row only when its successor is literally the
next calendar day. On 2023 that drops 65 rows. Small, but it is the kind of
defect that never announces itself.

## Problem 4 — the operational end lags ~6 months

`daily_44201_2026.zip` exists but ends 2026-03-31. So "operational" data cannot
be genuinely real-time through this source.

**Assessment: acceptable, and worth stating plainly.** This domain's shift is
seasonal and physical; there is no adversary adapting to the forecast, so a
months-old operational sample is still a fair test of deployment-era
performance. What matters is that the operational years are *after* the
benchmark era and processed as raw data rather than a curated extract. If
genuinely recent data is wanted later, AirNow or OpenAQ provide it — both need a
free API key, which is why neither is used for the reproducible core.

---

## Consequences for the protocol

1. The unit of analysis is the **airshed**, not a station. `PREREGISTRATION.md`
   is amended accordingly (addendum dated today; the original text is not
   edited).
2. Confidence intervals **cluster on date**. Block bootstrap over consecutive
   days remains appropriate for the temporal-split evaluation; date-clustering
   handles the within-day correlation across sites. Both are needed — they
   address different dependencies.
3. Two feature tiers, both reported.
4. Benchmark era and operational era to be fixed before modelling, with the
   constraint that **no era may contain a year with zero exceedances** at the
   pooled level (this is a data-quality gate, not a result-dependent choice —
   analogous to phish-drift's fail-closed label gate).

## Reproducing the spike

```bash
pip install -r requirements.txt
python -c "
from pathlib import Path
from ozonedrift.aqs import build_features, summarise
for tier in ('core','extended'):
    print(tier, summarise(build_features([2023], Path('data/cache'), tier=tier)))
"
```

Downloads ~16 MB on first run and caches under `data/cache/`.
