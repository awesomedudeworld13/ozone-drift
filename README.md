# ozone-drift

**Question: when a machine-learning model scores well on a test set, does that score still hold up once the model is used for real?**

For Houston smog forecasting, the answer is **yes — as long as you test the model honestly.** Almost all of the apparent drop-off turns out to come from one careless testing habit, not from the world changing.

---

## What this is, in plain terms

We predict whether tomorrow's ground-level ozone (smog) will break the federal health limit at a monitoring station in the Houston area. Ozone is worth predicting: it triggers asthma attacks, and Houston has some of the worst levels in the country.

But the real subject here isn't smog. It's **how machine-learning results get tested**, and whether a published score means what people think it means. Smog is the test case — one of several in a larger study (see [the bigger picture](#the-bigger-picture) below).

### The score we use, and why

We report **TSS** (True Skill Statistic). It works like this:

> TSS = (fraction of real smog days you caught) − (fraction of clean days you falsely alarmed on)

TSS is **0 for a model with no skill at all**, and 1 for a perfect one. That zero point is the whole reason we use it.

**We deliberately don't lead with accuracy**, because accuracy lies here. Smog days are rare — about 2% of days. A model that just says "no smog tomorrow," every single day, forever, is **98% accurate** and completely worthless. Its TSS is 0, which correctly calls it what it is.

---

## The result

We pooled 17 monitoring stations across the Houston–Galveston–Brazoria area: 49,882 station-days, 1,008 of them smog days. We trained on 2015–2019 and treated 2022–2025 as real-world data the model had never seen.

Then we scored the same model three ways:

| How we tested it | What that means | TSS |
|---|---|---|
| **1. Shuffle all the days randomly**, train on 70%, test on the rest | what most published papers do | **0.808** |
| **2. Train on earlier days, test on later days** | the honest way to test a forecast | **0.593** |
| **3. Run it on 2022–2025**, years it never saw | actual deployment | **0.670** |

Read the gaps between those rows:

| Step | Change in TSS |
|---|---|
| Shuffled testing → honest testing | **−0.215** |
| Honest testing → real-world years | **+0.077** *(it got better)* |

**The shuffling is the whole problem.** Testing on randomly shuffled days makes the model look 0.215 better than it really is. Once you test it properly, moving to real-world data costs nothing — the model actually scored *higher* on 2022–2025 than on its own 2019 test.

### Why shuffling inflates the score

Two reasons, both easy to miss:

1. **Weather doesn't reset at midnight.** Tuesday's conditions look a lot like Monday's. If you shuffle days, Monday can land in training while Tuesday lands in testing. The model isn't forecasting — it's recognizing a day it has nearly already seen.

2. **A smog day hits the whole city at once.** When ozone spikes, it spikes at most of the 17 stations together. Shuffle the rows and some of those stations land in training while the rest land in testing. Same day, same weather — the model has already been shown the answer.

Training on earlier days and testing on later ones removes both problems. That is all "honest testing" means here.

---

## Does feeding it newer data help?

A natural fix when a model degrades is "just retrain it on recent data." We tested that directly, and for this problem it is **the wrong instinct — retraining on recent data made things worse.**

| Model trained on | Scored on 2015–2019 | Scored on 2022–2025 |
|---|---|---|
| 2015–2019 (older data) | 0.593 | **0.637** |
| 2022–2025 (newer data) | 0.539 | **0.501** |

On exactly the same recent test days, the model trained on *older* data scored **0.637** and the model trained on *newer* data scored **0.501**.

That is a drop of **0.136**, and the error bar runs from −0.255 to −0.009 — it stays below zero, so this is not noise. The older, larger training set simply generalizes better.

**Honest caveat:** the recent period has fewer days to train on, so some of this could be "less data" rather than "wrong data." Separating those two needs a test at several training-set sizes, which this project has not done yet.

This matches what the companion solar-flare project found: retraining on newer data does not close the gap there either.

---

## Is the model actually any good?

Worth checking, because a bad model can still produce an interesting-looking comparison.

The obvious cheap forecast is **"tomorrow will be like today"** — no machine learning, just repeat today's reading. That scores TSS **0.257** on the real-world years. Our model scores **0.670**. So it is doing real work.

The inputs it leans on most are today's ozone level, the time of year, wind direction, and the day's high temperature. Those are what an atmospheric chemist would expect to matter, which is reassuring — it has not latched onto some accident in the data.

---

## Two versions, both reported

Humidity matters chemically for ozone, but only about a third of station-days report it. Requiring humidity throws away more than half the data and most of the stations.

| Version | Weather inputs | Station-days | Stations | Smog days |
|---|---|---|---|---|
| **core** | temperature, wind speed and direction, yesterday's ozone, calendar | 49,882 | 17 | 1,008 |
| **extended** | + humidity and dew point | 21,350 | 7 | 488 |

**We report both, always.** Picking whichever one produced the more interesting result after seeing them would be exactly the cherry-picking this project exists to criticize. We committed to reporting both before running anything.

---

## Predictions we wrote down in advance

Before building any model we committed five predictions to [PREREGISTRATION.md](PREREGISTRATION.md). The point of writing predictions down first is that a result only counts as evidence if it could have come out wrong.

**One failed and one had no answer. Both are reported as such.**

| | We predicted | We got | Verdict |
|---|---|---|---|
| O1 | smog days would be 4–15% of days | 2.0% | **FAILED** |
| O2 | shuffling would inflate the score by 0.02–0.25 | +0.215 | held |
| O3 | real-world drop would be under 0.15 | −0.077 (it improved) | held |
| O4 | ozone would drift least of the domains tested | it does | held |
| O5 | one scoring cutoff would degrade more than the other | neither degraded | **NO ANSWER** |

**O1 failed**, and an earlier draft of our notes overstated it — we had checked 2023 alone (4.2%) and called it a hit. Across all nine years it is 2.0%, below the range we predicted. 2023 was simply a bad smog year; 2016 ran at 0.6%. The failure is recorded, and it sharpens the point about accuracy: at a 2% rate, "never predict smog" scores 98%.

We also found something we had **not** predicted, and flag it as such: the shuffling problem hurts one scoring cutoff about twice as much as the other (0.430 vs 0.215).

---

## The bigger picture

This is one of several test cases in a study asking: *does a benchmark score overstate real performance, and does that depend on what kind of change the model faces?*

Each domain was picked for a **different kind of change between test data and the real world**:

| Domain | What changes | Inflation from shuffling | Real-world drop | Total |
|---|---|---|---|---|
| **Ozone** (this repo) | seasons and weather — nothing adversarial | +0.215 | **−0.077** | **+0.138** |
| [Solar flares](https://github.com/solarflarepredictor-cmd/SolarFlarePredictor) | the Sun's 11-year cycle | +0.118 | +0.107 | **+0.225** |
| [Phishing URLs](https://github.com/awesomedudeworld13/phish-drift) | attackers actively adapting, plus a broken dataset | +0.0001 to +0.088 | +0.009 | **+0.508 to +0.996** |

Ozone is the **control**. Nothing here is fighting back: the atmosphere in 2026 follows the same chemistry it followed in 2016, no one is trying to evade a smog forecast, and the monitoring network is stable and public.

That is why a *small* result here is the valuable one. If even this domain collapsed, the problem would look universal and unfixable. Instead it holds up — which tells you the conditions under which a benchmark score **can** be trusted, something no collapsing domain can establish on its own.

---

## How we kept ourselves honest

- **Error bars group whole days together.** When estimating uncertainty we resample entire days rather than individual station readings, because 17 stations recording the same smog event are really *one* observation, not 17. Treating them as 17 would make our error bars look several times tighter than they should. Every domain in the study has its own version of this: solar groups by sunspot region, phishing by website domain.
- **The warning cutoff is locked before testing.** A model outputs a probability, and you pick a cutoff above which you issue a warning. Choosing that cutoff using the same data you are about to report on makes any model look better than it is. We pick it on a separate slice of earlier data, then freeze it.
- **Years with zero smog days are excluded up front.** TSS cannot be computed when nothing happened. We check this before building any model, so it is a property of the data rather than a convenient choice made after seeing results.
- **`RESULTS.md` is generated, never hand-edited.** Every number is rebuilt from the raw EPA files by script.

---

## Data

All public, no signup required:

| | |
|---|---|
| Ozone and weather | [EPA Air Quality System annual files](https://aqs.epa.gov/aqsweb/airdata/) — no API key needed, unlike EPA's other interface |
| Health limit | NAAQS 8-hour ozone standard, 0.070 ppm (2015) |

One limitation worth stating: EPA publishes these files about six months behind, so our real-world data currently runs through March 2026 rather than today. For this domain that is acceptable — nobody is adapting to evade a smog forecast, so months-old data is still a fair test. Genuinely live data is available from AirNow or OpenAQ, but both need an API key, which would make the project harder to reproduce.

---

## Running it yourself

```bash
pip install -r requirements.txt

python -m ozonedrift.cli fetch      # ~150 MB of EPA files, cached locally
python -m ozonedrift.cli survey     # coverage and smog-day counts per year
python -m ozonedrift.cli report     # the three tests -> RESULTS.md
python tests/test_protocol.py       # checks the method itself is sound
```

### Layout

```
ozonedrift/
  aqs.py          loads EPA data, builds the prediction inputs
  splits.py       shuffled vs chronological testing, the data-quality gate
  model.py        training, cutoff freezing, the "tomorrow = today" baseline
  evaluate.py     TSS and error bars          (SHARED — see below)
  gap.py          the three tests and the comparison
  cli.py          fetch / survey / report
tests/            checks on the method, run automatically on every change
```

### The shared scoring code

`ozonedrift/evaluate.py` is **character-for-character identical** to its counterpart in the phishing and solar-flare repos, apart from a comment at the top.

It is copied rather than imported so neither project needs the other installed. That has a real cost worth naming: **if the copies ever drift apart, the cross-domain comparison quietly stops being a comparison.** The whole study rests on every domain's TSS meaning the same thing.

`tests/test_protocol.py` checks this copy's fingerprint on every change, so a local edit fails immediately. It cannot catch an edit made in one of the other repos. When a fourth domain needs this code, pull it into a shared package rather than making a fourth copy.

### A note on the protocol

The original plan used a single monitoring station and predicted a 4–15% smog-day rate. The feature-availability check in [SPIKE.md](SPIKE.md) showed that does not work — the best-equipped station recorded **zero** smog days in 2016, and TSS cannot be computed for a year where nothing happened. Pooling the whole metro area fixed it. That change, and three others the check forced, are recorded as dated additions to the pre-registration rather than edited into the original text.
