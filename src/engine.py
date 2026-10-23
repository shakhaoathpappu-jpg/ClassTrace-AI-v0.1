"""Rule-based event validation and attendance calculations."""
from __future__ import annotations

import pandas as pd

VALID_ZONES = {"CAMPUS", "CLASS_A"}
VALID_TYPES = {"ENTRY", "EXIT"}

def normalize_events(events: pd.DataFrame) -> pd.DataFrame:
    df = events.copy()
    required = {"event_id", "student_id", "zone", "event_type", "timestamp"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["student_id"] = df["student_id"].astype(str)
    df["zone"] = df["zone"].astype(str).str.upper()
    df["event_type"] = df["event_type"].astype(str).str.upper()
    if "source" not in df:
        df["source"] = "UNKNOWN"
    if "is_synthetic" not in df:
        df["is_synthetic"] = False
    if "ground_truth_event" not in df:
        df["ground_truth_event"] = pd.NA
    return df.sort_values(["student_id", "zone", "timestamp", "event_id"], na_position="last").reset_index(drop=True)

def validate_events(events: pd.DataFrame) -> pd.DataFrame:
    """Flag suspicious records. Flags are heuristic, not definitive judgments."""
    df = normalize_events(events)
    df["flags"] = ""
    df["status"] = "OK"

    # Invalid fields / timestamp.
    bad_time = df["timestamp"].isna()
    df.loc[bad_time, "flags"] = "Invalid timestamp"
    df.loc[bad_time, "status"] = "REVIEW"

    bad_zone = ~df["zone"].isin(VALID_ZONES)
    df.loc[bad_zone, "flags"] = df.loc[bad_zone, "flags"].apply(
        lambda x: f"{x}; " if x else ""
    ) + "Unknown zone"
    df.loc[bad_zone, "status"] = "REVIEW"

    bad_type = ~df["event_type"].isin(VALID_TYPES)
    df.loc[bad_type, "flags"] = df.loc[bad_type, "flags"].apply(
        lambda x: f"{x}; " if x else ""
    ) + "Unknown event type"
    df.loc[bad_type, "status"] = "REVIEW"

    # Duplicate: same student, zone, event type within 5 seconds.
    valid = df.dropna(subset=["timestamp"]).copy()
    for _, group in valid.groupby(["student_id", "zone", "event_type"], sort=False):
        idxs = group.index.tolist()
        previous_time = None
        for idx in idxs:
            current = df.at[idx, "timestamp"]
            if previous_time is not None and (current - previous_time).total_seconds() <= 5:
                existing = df.at[idx, "flags"]
                df.at[idx, "flags"] = (existing + "; " if existing else "") + "Possible duplicate within 5s"
                df.at[idx, "status"] = "REVIEW"
            previous_time = current

    # Alternation checks per student and zone. An ENTRY should be followed by EXIT and vice versa.
    # If a prior event is already suspicious, still evaluate the observed sequence for transparency.
    for (_, _), group in valid.groupby(["student_id", "zone"], sort=False):
        prev_type = None
        prev_idx = None
        for idx, row in group.iterrows():
            typ = row["event_type"]
            if typ not in VALID_TYPES:
                continue
            if prev_type == typ:
                existing = df.at[idx, "flags"]
                note = f"Unexpected repeated {typ} (possible missing opposite event)"
                df.at[idx, "flags"] = (existing + "; " if existing else "") + note
                df.at[idx, "status"] = "REVIEW"
            prev_type = typ
            prev_idx = idx

    # End-of-log open intervals: last event for each student/zone is ENTRY.
    for (_, _), group in valid.groupby(["student_id", "zone"], sort=False):
        if group.empty:
            continue
        last_idx = group.index[-1]
        if df.at[last_idx, "event_type"] == "ENTRY":
            existing = df.at[last_idx, "flags"]
            note = "Open interval at end of log (missing EXIT possible)"
            df.at[last_idx, "flags"] = (existing + "; " if existing else "") + note
            df.at[last_idx, "status"] = "REVIEW"

    df["flags"] = df["flags"].str.strip("; ")
    return df.sort_values(["timestamp", "student_id"], na_position="last").reset_index(drop=True)

def _intervals_for_group(group: pd.DataFrame, end_time: pd.Timestamp | None = None):
    """Pair ENTRY/EXIT events; unpaired events are not silently imputed."""
    group = group.dropna(subset=["timestamp"]).sort_values("timestamp")
    intervals = []
    opened = None
    for _, row in group.iterrows():
        typ = row["event_type"]
        if typ == "ENTRY":
            if opened is None:
                opened = row["timestamp"]
            # repeated ENTRY is not paired; validator flags it
        elif typ == "EXIT":
            if opened is not None and row["timestamp"] >= opened:
                intervals.append((opened, row["timestamp"]))
                opened = None
            # orphan EXIT is ignored and should be reviewed
    if opened is not None and end_time is not None and end_time > opened:
        # Do not auto-impute a session end by default; interval stays unclosed.
        pass
    return intervals

def calculate_attendance(events: pd.DataFrame, class_start: str = "10:00", class_end: str = "11:00") -> pd.DataFrame:
    df = normalize_events(events)
    ids = sorted(df["student_id"].dropna().unique().tolist())
    rows = []
    for sid in ids:
        s = df[df["student_id"] == sid]
        campus = _intervals_for_group(s[s["zone"] == "CAMPUS"])
        classes = _intervals_for_group(s[s["zone"] == "CLASS_A"])
        campus_minutes = sum((b - a).total_seconds() / 60 for a, b in campus)
        class_minutes_raw = sum((b - a).total_seconds() / 60 for a, b in classes)

        # Calculate overlap of class intervals with scheduled class window for each date.
        if not s.empty and s["timestamp"].notna().any():
            day = s["timestamp"].dropna().iloc[0].date()
            start_dt = pd.Timestamp(f"{day} {class_start}")
            end_dt = pd.Timestamp(f"{day} {class_end}")
            class_minutes = 0.0
            for a, b in classes:
                lo, hi = max(a, start_dt), min(b, end_dt)
                if hi > lo:
                    class_minutes += (hi - lo).total_seconds() / 60
            scheduled = max(0.0, (end_dt - start_dt).total_seconds() / 60)
        else:
            class_minutes, scheduled = 0.0, 60.0

        rows.append({
            "student_id": sid,
            "campus_minutes": round(campus_minutes, 1),
            "class_minutes": round(class_minutes, 1),
            "class_attendance_pct": round(100 * class_minutes / scheduled, 1) if scheduled else 0.0,
            "scheduled_class_minutes": round(scheduled, 1),
            "class_intervals_paired": len(classes),
            "campus_intervals_paired": len(campus),
        })
    return pd.DataFrame(rows)

def build_timeline(events: pd.DataFrame, student_id: str) -> pd.DataFrame:
    df = validate_events(events)
    df = df[df["student_id"] == student_id].copy()
    if df.empty:
        return df
    df["timeline_label"] = df["zone"] + " " + df["event_type"]
    return df.sort_values("timestamp")
