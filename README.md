# ClassTrace AI v0.1

A free, local, rule-based prototype for cross-zone student attendance verification.
**All default records are synthetic demo data, not real student records.**

## Features
- Campus and classroom entry/exit events
- Student-wise attendance report
- Timeline for a selected student
- Rule-based checks for duplicate events, invalid event sequences, and missing-event suspicions
- Synthetic-data evaluation against known simulated ground truth
- Local CSV export

## Requirements
- Windows 10/11
- Python 3.10+ recommended
- VS Code

## Run on Windows (PowerShell terminal)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

If PowerShell blocks activation, you can skip activation and use:
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open the local URL Streamlit prints (usually http://localhost:8501).

## What the demo does
- Creates deterministic synthetic events for fictional IDs such as STU001.
- Calculates campus presence from campus ENTRY/EXIT pairs.
- Calculates classroom presence from CLASS ENTRY/EXIT pairs.
- Flags suspicious events. A flag is not proof that a student did anything wrong.
- Shows a synthetic-data sanity check against known simulated intervals.

## Important limitations
- This v0.1 is a software prototype, not a deployed school surveillance system.
- Synthetic performance does not demonstrate real-world accuracy.
- The simple event rules can be wrong when events are missing, duplicated, out of order, or when several people pass a sensor together.
- Missing-event detection is necessarily heuristic when there is no independent ground truth.
- Do not use the demo to make disciplinary decisions.
- If piloting with real people, obtain institutional approval and informed consent, minimize collected data, use pseudonymous IDs, protect access, and define a short retention period.

## Suggested project structure
- `app.py`: Streamlit UI
- `src/engine.py`: rule-based event processing and duration calculations
- `src/synthetic.py`: reproducible synthetic event generator
- `data/`: optional local exports (not required to run)
