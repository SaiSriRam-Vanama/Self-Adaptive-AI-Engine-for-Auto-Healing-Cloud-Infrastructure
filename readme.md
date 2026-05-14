# Auto-Healing AI — Self-Healing Server Monitoring & Anomaly Detection System

## Description

Auto-Healing AI is an intelligent, self-healing server monitoring system that continuously tracks server metrics (CPU, memory, error rate), detects anomalies using machine learning (Isolation Forest), predicts future risks using trend analysis, and autonomously executes healing actions — all presented through a real-time PyQt5 live dashboard.

**Purpose:** Eliminate manual server monitoring and incident response by automating detection, diagnosis, and remediation.

**Problem It Solves:** Traditional monitoring tools only alert humans when something goes wrong. Auto-Healing AI goes further — it detects anomalous behavior, predicts emerging risks, and takes automated corrective actions (scaling resources, restarting services, reallocating loads) without human intervention, reducing downtime and operational overhead.

**Patent:** This project's self-healing methodology and dual-engine comparative monitoring architecture are protected under patent. All rights reserved.

---

## Features

- **Real-time server metrics monitoring** — CPU, Memory, and Error rate tracking for 4+ servers
- **ML-based anomaly detection** — Isolation Forest algorithm identifies outliers in server behavior
- **Risk prediction engine** — Weighted scoring + linear trend analysis forecasts future risk levels (Low / Medium / High)
- **Automated self-healing** — Triggers corrective actions (scale CPU, restart memory-intensive services, restart faulty processes) when anomalies are detected
- **Dual-engine architecture** — Compare normal (No Injection) vs failure-injected (Injected) engines side-by-side to validate detection accuracy
- **Live PyQt5 dashboard** — Real-time graphs (pyqtgraph), snapshot bar charts (matplotlib), server metrics tables, and scrollable log viewer
- **Failure injection mode** — Intentionally injects CPU spikes and error surges to test and validate the healing engine
- **Graph comparison tool** — Automatically detects and highlights differences between normal and injected engine behavior
- **Comprehensive report generation** — Auto-generated reports with charts (bar, pie, timeline), CSV exports, and incident summaries
- **Alert cooldown mechanism** — Prevents alert fatigue by enforcing configurable cooldown periods per issue per server
- **Incident & risk logging** — All events persisted as JSONL files for audit and post-mortem analysis
- **Pytest test suite** — Unit tests for core engine components

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.8+ |
| UI Framework | PyQt5 |
| Real-time Charts | PyQtGraph |
| Static Charts | Matplotlib |
| Data Processing | Pandas, NumPy |
| Anomaly Detection | Scikit-learn (Isolation Forest) |
| Testing | Pytest |
| Logging | JSONL (JSON Lines) |

---

## Installation

### Prerequisites

- Python 3.8 or higher
- pip (Python package installer)
- (Optional) Virtual environment — recommended

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/saisriramv/auto-healing-ai.git
cd auto-healing-ai

# 2. (Recommended) Create and activate a virtual environment
python -m venv venv
.\venv\Scripts\activate    # Windows
source venv/bin/activate   # Linux / macOS

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the live dashboard
cd ui
python auto_healing_ui.py
```

---

## Usage

### Live Dashboard

1. Launch the UI: `cd ui && python auto_healing_ui.py`
2. Click **"Start No Injection"** to begin monitoring with normal metrics
3. Click **"Start Injected"** to begin monitoring with injected failures (CPU spikes, error surges)
4. Watch real-time graphs, tables, and logs update automatically
5. Use the **"Compare Graphs"** button to detect differences between engines
6. Stop both engines, then click **"Generate Reports"** to create comprehensive reports
7. View reports directly in the dashboard or open the `reports/` folder
8. Use **"Export Comparison"** to save comparison data as CSV

### CLI Mode (Headless Monitoring)

```bash
python app.py --cycles 10 --sleep 2
```

Runs 10 monitoring cycles with 2-second intervals between each cycle, generating metrics snapshots and logs.

### Running Tests

```bash
pytest tests/tests_engine.py -v
```

---

## Environment Variables

Create a `.env` file in the project root (optional overrides):

```env
# Anomaly detection sensitivity (0.0 - 0.5, default: 0.15)
CONTAMINATION=0.15

# Error rate threshold for alerts (default: 3.0)
ERROR_THRESHOLD=3.0

# Cooldown between same-issue alerts in seconds (default: 5)
COOLDOWN_SECONDS=5

# Number of history cycles for risk prediction (default: 10)
HISTORY_LENGTH=10

# Window size for moving averages (default: 5)
RISK_WINDOW_SIZE=5

# Enable/disable failure injection (default: True)
INJECT_FAILURES=True
```

---

## Folder Structure

```
auto-healing-ai/
├── app.py                  # CLI entry point — runs monitoring cycles
├── config.py               # Central configuration (servers, thresholds)
├── engine.py               # Core engine: metrics, anomaly detection, healing
├── engine_inject.py        # Extended engine with failure injection
├── risk_prediction.py      # Risk scoring and trend analysis
├── risk_utils.py           # Utility functions (moving average, trend, score)
├── requirements.txt        # Python dependencies
├── logs/                   # Incident and risk warning logs (JSONL)
│   ├── incidents.jsonl
│   ├── incidents_inject.jsonl
│   ├── risk_warnings.jsonl
│   └── incidents.log
├── reports/                # Generated reports and charts
│   ├── auto_healing_report_*.txt
│   ├── metrics_*.csv
│   ├── comparison_*.csv
│   ├── cpu_comparison_bar_*.png
│   ├── memory_comparison_bar_*.png
│   ├── incident_timeline.png
│   └── ...
├── tests/
│   └── tests_engine.py     # Pytest unit tests
├── ui/
│   ├── auto_healing_ui.py  # PyQt5 live dashboard
│   └── analyze_logs.py     # Log analysis and report generation
└── README.md
```

---

## Contributing

Contributions are welcome! Since this project is patent-protected, please follow these guidelines:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

For major changes, please open an issue first to discuss what you would like to change.

---

## License

MIT License — see the [LICENSE](LICENSE) file for details.

---

## Patent

This project's self-healing methodology, dual-engine comparative monitoring architecture, and automated anomaly remediation system are protected under patent. All rights reserved. Unauthorized use, reproduction, or distribution of the patented technology is prohibited.

---

## Author

**Vanama Sai Sri Ram**

- Email: saisriram2796@gmail.com
- LinkedIn: [saisriramv](https://linkedin.com/in/saisriramv)
- GitHub: [saisriramv](https://github.com/saisriramv)

---

*Built with Python, PyQt5, and Machine Learning*
