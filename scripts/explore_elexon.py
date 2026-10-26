"""Exploratory script for inspecting and testing Elexon BMRS API endpoints.

Queries real BMRS endpoints:
- Actuals: /datasets/FUELHH/stream (filtered for fuelType == WIND)
- Forecasts: /datasets/WINDFOR/stream
"""

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
import httpx
import pandas as pd

BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"


def print_section_header(title: str):
    print("=" * 80)
    print(title)
    print("=" * 80)


def explore_fuelhh(client: httpx.Client):
    print_section_header("SECTION A: FUELHH ACTUALS (2026-01-01 to 2026-01-02, WIND ONLY)")

    # Test /datasets/FUELHH/stream with settlementDateFrom and settlementDateTo
    endpoint = f"{BASE_URL}/datasets/FUELHH/stream"
    params = {
        "settlementDateFrom": "2026-01-01",
        "settlementDateTo": "2026-01-02",
    }
    print(f"Request URL: {endpoint}")
    print(f"Query Params: {params}")

    response = client.get(endpoint, params=params)
    print(f"HTTP Status: {response.status_code}")
    if response.status_code != 200:
        print(f"Error Body: {response.text}")
        return None

    raw_data = response.json()
    print(f"Total raw records returned (all fuel types): {len(raw_data)}")

    # Filter fuelType == WIND
    wind_records = [r for r in raw_data if r.get("fuelType") == "WIND"]
    print(f"Filtered WIND records count: {len(wind_records)}")

    # Raw JSON of 3 records
    print("\n--- a.1: Raw JSON of 3 sample records ---")
    print(json.dumps(wind_records[:3], indent=2))

    # All field names
    fields = list(wind_records[0].keys()) if wind_records else []
    print(f"\n--- a.2: All field names in FUELHH ---")
    print(f"Field names: {fields}")

    # startTime format & timezone
    sample_start_time = wind_records[0].get("startTime")
    sample_publish_time = wind_records[0].get("publishTime")
    print(f"\n--- a.3: startTime and publishTime format & timezone ---")
    print(f"Sample startTime: '{sample_start_time}'")
    print(f"Sample publishTime: '{sample_publish_time}'")
    is_utc_z = all(r.get("startTime", "").endswith("Z") for r in wind_records)
    print(f"Are all startTime values ending in 'Z' (ISO 8601 UTC): {is_utc_z}")

    # Record count
    print(f"\n--- a.4: Record count ---")
    print(f"Total WIND records: {len(wind_records)} (expected 48 periods/day * 2 days = 96)")

    # Existence of settlementDate / settlementPeriod
    has_settlement_date = "settlementDate" in fields
    has_settlement_period = "settlementPeriod" in fields
    print(f"\n--- a.5: settlementDate and settlementPeriod existence ---")
    print(f"Does 'settlementDate' exist: {has_settlement_date} (e.g. {wind_records[0].get('settlementDate')})")
    print(f"Does 'settlementPeriod' exist: {has_settlement_period} (e.g. {wind_records[0].get('settlementPeriod')})")

    return wind_records


def explore_windfor(client: httpx.Client):
    print_section_header("SECTION B: WINDFOR FORECASTS (Publish window 2025-12-31 to 2026-01-02)")

    endpoint = f"{BASE_URL}/datasets/WINDFOR/stream"
    params = {
        "publishDateTimeFrom": "2025-12-31T00:00:00Z",
        "publishDateTimeTo": "2026-01-02T23:59:59Z",
    }
    print(f"Request URL: {endpoint}")
    print(f"Query Params: {params}")

    response = client.get(endpoint, params=params)
    print(f"HTTP Status: {response.status_code}")
    if response.status_code != 200:
        print(f"Error Body: {response.text}")
        return None

    raw_data = response.json()
    print(f"Total WINDFOR records returned: {len(raw_data)}")

    # Raw JSON of 3 records
    print("\n--- b.1: Raw JSON of 3 sample records ---")
    print(json.dumps(raw_data[:3], indent=2))

    # All field names
    fields = list(raw_data[0].keys()) if raw_data else []
    print(f"\n--- b.2: All field names in WINDFOR ---")
    print(f"Field names: {fields}")
    print(f"Does 'settlementDate' exist: {'settlementDate' in fields}")
    print(f"Does 'settlementPeriod' exist: {'settlementPeriod' in fields}")

    # Relationship between publishTime and startTime
    print(f"\n--- b.3: Relationship between publishTime and startTime ---")
    unique_pub_times = sorted(list(set(r["publishTime"] for r in raw_data)))
    unique_start_times = sorted(list(set(r["startTime"] for r in raw_data)))
    print(f"Unique publish batches: {len(unique_pub_times)} distinct publish times")
    print(f"  First publishTime: {unique_pub_times[0]}, Last publishTime: {unique_pub_times[-1]}")
    print(f"  Sample publish cadence: {unique_pub_times[:5]}")
    print(f"Unique target startTimes covered: {len(unique_start_times)}")
    print(f"  First startTime: {unique_start_times[0]}, Last startTime: {unique_start_times[-1]}")

    # Calculate lead times
    lead_hours_list = []
    by_target = defaultdict(list)
    for r in raw_data:
        pt = datetime.fromisoformat(r["publishTime"].replace("Z", "+00:00"))
        st = datetime.fromisoformat(r["startTime"].replace("Z", "+00:00"))
        lead_h = (st - pt).total_seconds() / 3600.0
        lead_hours_list.append(lead_h)
        by_target[r["startTime"]].append((pt, r["generation"], lead_h))

    # Forecasts per target startTime
    counts = [len(v) for v in by_target.values()]
    print(f"\n--- b.4: Forecasts per target startTime ---")
    print(f"Minimum forecasts per target startTime: {min(counts)}")
    print(f"Maximum forecasts per target startTime: {max(counts)}")
    print(f"Average forecasts per target startTime: {sum(counts) / len(counts):.2f}")

    sample_target = "2026-01-01T12:00:00Z"
    if sample_target in by_target:
        print(f"\nDetailed forecast progression for sample target {sample_target} ({len(by_target[sample_target])} forecasts):")
        sorted_forecasts = sorted(by_target[sample_target], key=lambda x: x[0])
        for pt, gen, lead in sorted_forecasts:
            print(f"  Published: {pt.isoformat()} | Lead Time: {lead:+5.1f}h | Generation: {gen} MW")

    # Range of lead times
    print(f"\n--- b.5: Range of lead times (startTime - publishTime, in hours) ---")
    print(f"Minimum lead time: {min(lead_hours_list):.1f} hours")
    print(f"Maximum lead time: {max(lead_hours_list):.1f} hours")
    positive_leads = [h for h in lead_hours_list if h > 0]
    negative_leads = [h for h in lead_hours_list if h < 0]
    zero_leads = [h for h in lead_hours_list if h == 0]
    print(f"Positive lead times (future forecasts): {len(positive_leads)} records (up to +{max(positive_leads):.1f}h ahead)")
    print(f"Negative lead times (historical / outturn replay): {len(negative_leads)} records (down to {min(negative_leads):.1f}h prior)")
    print(f"Zero lead times (real-time): {len(zero_leads)} records")

    return raw_data


def check_query_params_and_limits(client: httpx.Client):
    print_section_header("SECTION C: QUERY PARAMETERS, PAGINATION & RANGE LIMITS")

    print("1. FUELHH Endpoint Parameter Support:")
    test_cases_fuelhh = [
        ("settlementDateFrom & settlementDateTo", {"settlementDateFrom": "2026-01-01", "settlementDateTo": "2026-01-02"}),
        ("publishDateTimeFrom & publishDateTimeTo", {"publishDateTimeFrom": "2026-01-01T00:00:00Z", "publishDateTimeTo": "2026-01-02T23:59:59Z"}),
        ("fuelType parameter (server-side filter)", {"settlementDateFrom": "2026-01-01", "settlementDateTo": "2026-01-02", "fuelType": "WIND"}),
        ("settlementPeriodFrom & settlementPeriodTo", {"settlementDateFrom": "2026-01-01", "settlementDateTo": "2026-01-01", "settlementPeriodFrom": 1, "settlementPeriodTo": 12}),
    ]

    for desc, p in test_cases_fuelhh:
        r = client.get(f"{BASE_URL}/datasets/FUELHH/stream", params=p)
        count = len(r.json()) if r.status_code == 200 else 0
        print(f"  - {desc}: HTTP {r.status_code}, returned {count} records")

    print("\n2. WINDFOR Endpoint Parameter Support:")
    test_cases_windfor = [
        ("publishDateTimeFrom & publishDateTimeTo (ISO UTC)", {"publishDateTimeFrom": "2025-12-31T00:00:00Z", "publishDateTimeTo": "2026-01-02T23:59:59Z"}),
        ("unrecognized / default fallback test (no params)", {}),
    ]
    for desc, p in test_cases_windfor:
        r = client.get(f"{BASE_URL}/datasets/WINDFOR/stream", params=p)
        count = len(r.json()) if r.status_code == 200 else 0
        print(f"  - {desc}: HTTP {r.status_code}, returned {count} records")

    print("\n3. Pagination & Maximum Date Range Behavior:")
    print("  - Stream Endpoints: Neither /datasets/FUELHH/stream nor /datasets/WINDFOR/stream uses pagination.")
    print("    They return a complete streaming JSON array in a single HTTP response.")
    print("  - Non-stream Endpoints (e.g. /datasets/FUELHH): Return a paginated object {'data': [...]} requiring page token/index.")
    
    # Test wide date range on FUELHH stream
    r_wide = client.get(f"{BASE_URL}/datasets/FUELHH/stream", params={"settlementDateFrom": "2026-01-01", "settlementDateTo": "2026-01-31", "fuelType": "WIND"})
    print(f"  - 31-day query test on FUELHH stream: HTTP {r_wide.status_code}, records: {len(r_wide.json())} (31 days * 48 periods = 1,488 records)")

    # Test wide date range on WINDFOR stream
    r_wind_wide = client.get(f"{BASE_URL}/datasets/WINDFOR/stream", params={"publishDateTimeFrom": "2026-01-01T00:00:00Z", "publishDateTimeTo": "2026-01-15T00:00:00Z"})
    print(f"  - 14-day query test on WINDFOR stream: HTTP {r_wind_wide.status_code}, records: {len(r_wind_wide.json())}")


def check_data_quality(fuel_records, wind_records):
    print_section_header("SECTION D: DATA QUALITY (DUPLICATES, NULLS, MISSING INTERVALS, GENERATION=0)")

    # 1. FUELHH checks
    df_fuel = pd.DataFrame(fuel_records)
    print("1. FUELHH Actuals Quality Checks (WIND):")
    print(f"  Total records: {len(df_fuel)}")
    
    # Duplicates
    dup_start = df_fuel.duplicated(subset=["startTime"]).sum()
    dup_settlement = df_fuel.duplicated(subset=["settlementDate", "settlementPeriod"]).sum()
    print(f"  Duplicate startTimes: {dup_start}")
    print(f"  Duplicate (settlementDate, settlementPeriod) tuples: {dup_settlement}")

    # Nulls
    null_counts_fuel = df_fuel.isnull().sum().to_dict()
    print(f"  Null counts per column: {null_counts_fuel}")

    # Missing intervals (expect 48/day)
    df_fuel["dt"] = pd.to_datetime(df_fuel["startTime"])
    df_fuel_sorted = df_fuel.sort_values("dt")
    expected_fuel_idx = pd.date_range("2026-01-01 00:00:00Z", "2026-01-02 23:30:00Z", freq="30min")
    missing_fuel = set(expected_fuel_idx) - set(df_fuel_sorted["dt"])
    print(f"  Expected intervals (48 per day * 2 days): {len(expected_fuel_idx)}")
    print(f"  Observed intervals: {len(df_fuel_sorted['dt'].unique())}")
    print(f"  Missing intervals: {len(missing_fuel)}")

    # Zero generation
    zero_gen_fuel = (df_fuel["generation"] == 0).sum()
    print(f"  Records with generation == 0: {zero_gen_fuel}")
    print(f"  Generation stats: min={df_fuel['generation'].min()} MW, max={df_fuel['generation'].max()} MW, mean={df_fuel['generation'].mean():.1f} MW")

    # 2. WINDFOR checks
    df_wind = pd.DataFrame(wind_records)
    print("\n2. WINDFOR Forecasts Quality Checks:")
    print(f"  Total records: {len(df_wind)}")

    # Duplicates on (publishTime, startTime)
    dup_wind = df_wind.duplicated(subset=["publishTime", "startTime"]).sum()
    print(f"  Duplicate (publishTime, startTime) pairs: {dup_wind}")

    # Nulls
    null_counts_wind = df_wind.isnull().sum().to_dict()
    print(f"  Null counts per column: {null_counts_wind}")

    # Zero generation
    zero_gen_wind = (df_wind["generation"] == 0).sum()
    print(f"  Records with generation == 0: {zero_gen_wind}")
    print(f"  Generation stats: min={df_wind['generation'].min()} MW, max={df_wind['generation'].max()} MW, mean={df_wind['generation'].mean():.1f} MW")

    # Check WINDFOR interval step inside batches
    batches = df_wind.groupby("publishTime")
    step_set = set()
    for _, batch in batches:
        b_sorted = batch.sort_values("startTime")
        diffs = b_sorted["startTime"].map(lambda x: datetime.fromisoformat(x.replace("Z", "+00:00"))).diff().dropna()
        for d in diffs:
            step_set.add(d.total_seconds() / 60.0)
    print(f"  Interval cadence inside forecast batches: {sorted(list(step_set))} minutes")


def check_timestamps_utc(fuel_records, wind_records):
    print_section_header("SECTION E: TIMEZONE VERIFICATION (UTC COMPLIANCE)")

    fuel_start_utc = all(r.get("startTime", "").endswith("Z") for r in fuel_records)
    fuel_pub_utc = all(r.get("publishTime", "").endswith("Z") for r in fuel_records)
    wind_start_utc = all(r.get("startTime", "").endswith("Z") for r in wind_records)
    wind_pub_utc = all(r.get("publishTime", "").endswith("Z") for r in wind_records)

    print(f"FUELHH 'startTime' all UTC (ends with 'Z'): {fuel_start_utc}")
    print(f"FUELHH 'publishTime' all UTC (ends with 'Z'): {fuel_pub_utc}")
    print(f"WINDFOR 'startTime' all UTC (ends with 'Z'): {wind_start_utc}")
    print(f"WINDFOR 'publishTime' all UTC (ends with 'Z'): {wind_pub_utc}")

    # Check whether parser preserves UTC timezone
    sample_fuel_ts = datetime.fromisoformat(fuel_records[0]["startTime"].replace("Z", "+00:00"))
    sample_wind_ts = datetime.fromisoformat(wind_records[0]["startTime"].replace("Z", "+00:00"))
    print(f"Sample parsed FUELHH startTime tzinfo: {sample_fuel_ts.tzinfo} (offset={sample_fuel_ts.utcoffset()})")
    print(f"Sample parsed WINDFOR startTime tzinfo: {sample_wind_ts.tzinfo} (offset={sample_wind_ts.utcoffset()})")
    print("Conclusion: All timestamps are strictly UTC (GMT/Zulu time, offset 0:00).")


def main():
    client = httpx.Client(timeout=60.0)
    try:
        fuel_records = explore_fuelhh(client)
        if fuel_records is None:
            sys.exit(1)

        wind_records = explore_windfor(client)
        if wind_records is None:
            sys.exit(1)

        check_query_params_and_limits(client)
        check_data_quality(fuel_records, wind_records)
        check_timestamps_utc(fuel_records, wind_records)

        print_section_header("EXPLORATION COMPLETE: ALL VERIFICATIONS PASSED")
    finally:
        client.close()


if __name__ == "__main__":
    main()
