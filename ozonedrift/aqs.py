"""EPA AQS data loading and forecast-time feature construction.

Data source
-----------
EPA's pre-generated annual files at https://aqs.epa.gov/aqsweb/airdata/. These
need **no API key**, unlike the AQS REST API, which is why they are used here:
the whole analysis must be reproducible by a reviewer with nothing but a network
connection. One zip per pollutant per year, ~4 MB each.

Files used, all keyed by ``State Code`` / ``County Code`` / ``Site Num``:

    daily_44201_<year>.zip   ozone, as 8-hour running average
    daily_TEMP_<year>.zip    outdoor temperature
    daily_WIND_<year>.zip    wind speed and direction (resultant)
    daily_RH_DP_<year>.zip   relative humidity and dew point

Target
------
``1st Max Value`` on the ozone file's ``8-HR RUN AVG BEGIN HOUR`` rows is the
daily maximum 8-hour ozone concentration -- exactly the quantity the NAAQS
standard (0.070 ppm) is written against, so the label needs no reconstruction.

Forecast-time discipline
------------------------
Every feature is measured on day D and the label is exceedance on day D+1. The
model never sees same-day ozone or any future meteorology. ``build_features``
additionally drops any row whose successor is not literally the next calendar
day, so a gap in a site's record can never silently become a two-day-ahead
forecast labelled as one-day-ahead.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

AIRDATA = "https://aqs.epa.gov/aqsweb/airdata/{stem}.zip"

# NAAQS 8-hour ozone standard (2015), in ppm. The label threshold.
NAAQS_8H_OZONE_PPM = 0.070

# Houston-Galveston-Brazoria. Harris (201) is the core; the rest complete the
# nonattainment area so the pooled sample is a coherent airshed rather than an
# arbitrary radius.
TEXAS = "48"
HGB_COUNTIES = ("201", "039", "071", "167", "291", "473")

# Parameter names as they appear in the AQS files, grouped by source file.
# Note the trailing space in "Relative Humidity " -- it is in the upstream data
# and matching without it silently yields an empty frame.
MET_SOURCES = {
    "TEMP": ["Outdoor Temperature"],
    "WIND": ["Wind Speed - Resultant", "Wind Direction - Resultant"],
    "RH_DP": ["Relative Humidity ", "Dew Point"],
}

# Feature tiers. Relative humidity and dew point are genuinely informative for
# ozone chemistry, but they are reported at only ~34% of Houston site-days
# against ~63% for wind and ~87% for temperature. Requiring them costs roughly
# three quarters of the sample and two thirds of the monitoring sites. The study
# therefore runs a CORE tier across the full network and an EXTENDED tier on the
# subset that has humidity, and reports both -- rather than silently picking
# whichever produces the more interesting gap.
CORE_MET = ("outdoor_temperature", "wind_speed_resultant", "wind_direction_resultant")
EXTENDED_MET = CORE_MET + ("relative_humidity", "dew_point")

CALENDAR_FEATURES = ("doy_sin", "doy_cos", "day_of_week")


def download(stem: str, cache_dir: Path) -> Path:
    """Fetch one annual AQS file, caching by name. Returns the local path."""
    import requests

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / f"{stem}.zip"
    if dest.exists() and dest.stat().st_size > 100_000:
        return dest

    tmp = dest.with_suffix(".part")
    with requests.get(AIRDATA.format(stem=stem), stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
    # Guard against a truncated download being cached as if it were the dataset.
    if tmp.stat().st_size < 100_000:
        size = tmp.stat().st_size
        tmp.unlink()
        raise RuntimeError(f"{stem}: download was {size:,} bytes; source may have moved")
    tmp.replace(dest)
    return dest


def _read_area(path: Path) -> pd.DataFrame:
    """Read one annual file, filtered to the HGB airshed, with a site key."""
    with zipfile.ZipFile(path) as z:
        frame = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])), low_memory=False)

    frame["sc"] = frame["State Code"].astype(str).str.zfill(2)
    frame["cc"] = frame["County Code"].astype(str).str.zfill(3)
    frame = frame[(frame.sc == TEXAS) & (frame.cc.isin(HGB_COUNTIES))].copy()
    frame["site"] = frame.sc + "-" + frame.cc + "-" + frame["Site Num"].astype(str).str.zfill(4)
    frame["date"] = pd.to_datetime(frame["Date Local"])
    return frame


def load_ozone(year: int, cache_dir: Path) -> pd.DataFrame:
    """Daily maximum 8-hour ozone per site, one row per site-day."""
    frame = _read_area(download(f"daily_44201_{year}", cache_dir))
    # A site can report several POCs (parallel instruments) for the same day.
    # Keep the highest reading: the NAAQS design value is defined on the maximum,
    # and averaging instruments would understate exceedances.
    frame = frame.sort_values("1st Max Value", ascending=False)
    frame = frame.drop_duplicates(["site", "date"])
    return frame[["site", "date", "1st Max Value", "Latitude", "Longitude"]].rename(
        columns={"1st Max Value": "o3_max8h"}
    )


def load_meteorology(year: int, cache_dir: Path) -> pd.DataFrame:
    """Co-located meteorology per site-day, wide format.

    Joined on site number, not geographic proximity. EPA co-locates most met
    instruments with the ozone monitor at the same site, so an exact join is
    available and is preferable to nearest-neighbour matching, which would
    introduce a distance-dependent error that varies by site and year.
    """
    out: pd.DataFrame | None = None
    for stem, parameters in MET_SOURCES.items():
        frame = _read_area(download(f"daily_{stem}_{year}", cache_dir))
        for parameter in parameters:
            column = parameter.strip().lower().replace(" - ", "_").replace(" ", "_")
            sub = frame[frame["Parameter Name"] == parameter]
            # Prefer the most complete instrument-day when several report.
            sub = sub.sort_values("Observation Percent", ascending=False)
            sub = sub.drop_duplicates(["site", "date"])
            sub = sub[["site", "date", "Arithmetic Mean", "1st Max Value"]].rename(
                columns={"Arithmetic Mean": f"{column}_mean", "1st Max Value": f"{column}_max"}
            )
            out = sub if out is None else out.merge(sub, on=["site", "date"], how="outer")
    return out if out is not None else pd.DataFrame(columns=["site", "date"])


def build_features(years, cache_dir: Path, tier: str = "core") -> pd.DataFrame:
    """Assemble the modelling frame: features on day D, exceedance on day D+1.

    ``tier`` selects ``CORE_MET`` (temperature and wind, available across the
    whole network) or ``EXTENDED_MET`` (adds humidity and dew point, available
    at roughly a third of site-days). Rows missing any feature in the selected
    tier are dropped, and the caller is told how many via the returned frame's
    ``attrs``.
    """
    if tier not in ("core", "extended"):
        raise ValueError(f"tier must be 'core' or 'extended', got {tier!r}")
    met_vars = CORE_MET if tier == "core" else EXTENDED_MET

    parts = []
    for year in years:
        ozone = load_ozone(year, cache_dir)
        met = load_meteorology(year, cache_dir)
        parts.append(ozone.merge(met, on=["site", "date"], how="left"))
    frame = pd.concat(parts, ignore_index=True).sort_values(["site", "date"])

    # Label: exceedance TOMORROW at the same site.
    frame["next_o3"] = frame.groupby("site")["o3_max8h"].shift(-1)
    frame["next_date"] = frame.groupby("site")["date"].shift(-1)
    # Only true consecutive days. A gap would otherwise become a multi-day-ahead
    # forecast wearing a one-day-ahead label -- an easier task scored as if it
    # were the stated one.
    consecutive = (frame.next_date - frame.date).dt.days == 1
    n_before = len(frame)
    frame = frame[consecutive].copy()
    frame["y"] = (frame.next_o3 > NAAQS_8H_OZONE_PPM).astype(np.int8)

    # Seasonality as a smooth cycle rather than a month integer, so December and
    # January are adjacent rather than maximally distant.
    doy = frame.date.dt.dayofyear
    frame["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    frame["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    # Weekday matters: precursor emissions follow commute traffic.
    frame["day_of_week"] = frame.date.dt.dayofweek

    feature_names = tuple(
        [f"{v}_{stat}" for v in met_vars for stat in ("mean", "max")]
        + ["o3_max8h"] + list(CALENDAR_FEATURES)
    )
    complete = frame.dropna(subset=list(feature_names)).copy()

    complete.attrs["feature_names"] = feature_names
    complete.attrs["tier"] = tier
    complete.attrs["dropped_non_consecutive"] = n_before - len(frame)
    complete.attrs["dropped_incomplete"] = len(frame) - len(complete)
    return complete


def summarise(frame: pd.DataFrame) -> dict:
    """Shape, coverage and base rate -- the numbers that decide feasibility."""
    return {
        "tier": frame.attrs.get("tier"),
        "rows": len(frame),
        "sites": int(frame.site.nunique()),
        "days": int(frame.date.nunique()),
        "years": sorted(frame.date.dt.year.unique().tolist()),
        "base_rate": round(float(frame.y.mean()), 6),
        "positives": int(frame.y.sum()),
        "dropped_non_consecutive": frame.attrs.get("dropped_non_consecutive"),
        "dropped_incomplete": frame.attrs.get("dropped_incomplete"),
        "n_features": len(frame.attrs.get("feature_names", ())),
    }
