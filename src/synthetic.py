"""Deterministic synthetic event generator for ClassTrace AI v0.1."""
from __future__ import annotations

import random
from datetime import datetime, date, time, timedelta
import pandas as pd

EVENT_COLUMNS = [
    "event_id", "student_id", "zone", "event_type", "timestamp",
    "source", "is_synthetic", "ground_truth_event"
]

def generate_synthetic_events(
    n_students: int = 12,
    day: date | None = None,
    seed: int = 7,
    include_faults: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (observed events, ground truth event log) using fictional students."""
    day = day or date(2026, 10, 22)
    rng = random.Random(seed)
    truth_rows = []
    observed_rows = []
    event_counter = 1

    def add_event(sid, zone, event_type, dt, source="SIMULATOR", truth=True):
        nonlocal event_counter
        row = {
            "event_id": f"EV{event_counter:05d}",
            "student_id": sid,
            "zone": zone,
            "event_type": event_type,
            "timestamp": dt,
            "source": source,
            "is_synthetic": True,
            "ground_truth_event": truth,
        }
        event_counter += 1
        return row

    for i in range(1, n_students + 1):
        sid = f"STU{i:03d}"
        # Each student has a known campus interval.
        campus_in = datetime.combine(day, time(8, 0)) + timedelta(minutes=rng.randint(0, 35))
        campus_out = datetime.combine(day, time(15, 0)) + timedelta(minutes=rng.randint(0, 45))
        student_truth = [
            add_event(sid, "CAMPUS", "ENTRY", campus_in),
            add_event(sid, "CAMPUS", "EXIT", campus_out),
        ]

        # A scheduled class from 10:00 to 11:00. Some students leave and return.
        class_in = datetime.combine(day, time(9, 55)) + timedelta(minutes=rng.randint(0, 8))
        class_out = datetime.combine(day, time(11, 0)) + timedelta(minutes=rng.randint(0, 3))
        class_events = [add_event(sid, "CLASS_A", "ENTRY", class_in)]
        if i % 3 == 0:
            leave = datetime.combine(day, time(10, 25)) + timedelta(minutes=rng.randint(0, 3))
            back = leave + timedelta(minutes=rng.randint(4, 10))
            class_events += [
                add_event(sid, "CLASS_A", "EXIT", leave),
                add_event(sid, "CLASS_A", "ENTRY", back),
            ]
        class_events.append(add_event(sid, "CLASS_A", "EXIT", class_out))
        student_truth += class_events
        truth_rows.extend(student_truth)

        for row in student_truth:
            # Introduce controlled sensor faults in observed log.
            if include_faults and rng.random() < 0.045:
                continue  # missing event
            observed_rows.append(dict(row, source=rng.choice(["RFID_SIM", "IR_SIM"])))
            if include_faults and rng.random() < 0.035:
                duplicate = dict(row)
                duplicate["event_id"] = f"EV{event_counter:05d}"
                event_counter += 1
                duplicate["source"] = "RFID_SIM_DUPLICATE"
                duplicate["timestamp"] = row["timestamp"] + timedelta(seconds=1)
                observed_rows.append(duplicate)

    # Add a deliberately out-of-sequence extra event for demo visibility.
    if include_faults and n_students >= 4:
        sid = "STU004"
        dt = datetime.combine(day, time(12, 0))
        observed_rows.append(add_event(sid, "CLASS_A", "EXIT", dt, source="SIM_FAULT", truth=False))

    observed = pd.DataFrame(observed_rows, columns=EVENT_COLUMNS)
    truth = pd.DataFrame(truth_rows, columns=EVENT_COLUMNS)
    if not observed.empty:
        observed = observed.sort_values(["timestamp", "student_id", "event_id"]).reset_index(drop=True)
    if not truth.empty:
        truth = truth.sort_values(["timestamp", "student_id", "event_id"]).reset_index(drop=True)
    return observed, truth
