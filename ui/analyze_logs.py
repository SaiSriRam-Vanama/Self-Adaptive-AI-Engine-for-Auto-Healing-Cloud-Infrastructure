import pandas as pd
import matplotlib.pyplot as plt
import os
import ast
from collections import defaultdict
from PyQt5.QtCore import QTimer
import sys
import subprocess

LOG_FILE = os.path.join("logs", "incidents.log")
RISK_LOG_FILE = os.path.join("logs", "risk_warnings.log")
REPORTS_DIR = "reports"

os.makedirs(REPORTS_DIR, exist_ok=True)

def normalize_issue(issue: str) -> str:
    """Normalize issue strings to standard format."""
    issue = issue.strip()
    if issue.startswith("Issue:"):
        return None  # Skip weird leftover strings
    mapping = {
        "High CPU": "High CPU Usage",
        "High CPU Usage": "High CPU Usage",
        "High Memory Usage": "High Memory Usage",
        "High Error Rate": "High Error Rate",
        "": None,
        ":": None,
        "Issue": None,
        # Add more mappings if needed
    }
    return mapping.get(issue, issue)

def clean_server(server: str) -> str:
    # Clean and normalize server names
    server = server.strip()
    # Remove entries like 'Server: server-3' or any prefix
    if server.lower().startswith("server:"):
        server = server.split(":", 1)[1].strip()
    return server

def analyze_incidents():
    print("Generating incident reports...")
    if not os.path.exists(LOG_FILE):
        print("No incident log file found. Run app.py first to generate logs.")
        return

    df = pd.read_csv(
        LOG_FILE,
        sep="|",
        names=["Time", "Server", "Issues", "Actions"],
        engine="python"
    )

    # Clean whitespace
    df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)

    # Clean Server column
    df["Server"] = df["Server"].apply(clean_server)

    # Remove rows with empty or NaN Server
    df = df[df["Server"].notna() & (df["Server"] != "")]

    # Convert Time column to datetime
    df["Time"] = pd.to_datetime(df["Time"], format="%Y-%m-%d %H:%M:%S", errors="coerce")

    print("\n===== Incident Summary =====")
    print(f"Total incidents: {len(df)}")
    print("\nIncidents per Server:")
    print(df["Server"].value_counts())

    # Parse and normalize issues for counts
    issue_counts = defaultdict(int)
    for issues_str in df["Issues"]:
        if pd.isna(issues_str):
            continue
        try:
            issues_list = ast.literal_eval(issues_str)
            if not isinstance(issues_list, list):
                issues_list = [str(issues_list)]
        except:
            clean_str = issues_str.strip("[]'\" ")
            issues_list = [i.strip() for i in clean_str.split(",") if i.strip()]

        for issue in issues_list:
            normalized = normalize_issue(issue)
            if normalized:
                issue_counts[normalized] += 1

    print("\nIncidents per Issue Type:")
    for issue, count in sorted(issue_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"{issue}: {count}")

    # Save summary report
    summary_path = os.path.join(REPORTS_DIR, "summary_report.txt")
    with open(summary_path, "w") as f:
        f.write("===== Incident Summary =====\n")
        f.write(f"Total incidents: {len(df)}\n\n")
        f.write("Incidents per Server:\n")
        for server, count in df["Server"].value_counts().items():
            f.write(f"{server}: {count}\n")
        f.write("\nIncidents per Issue Type:\n")
        for issue, count in sorted(issue_counts.items(), key=lambda x: x[1], reverse=True):
            f.write(f"{issue}: {count}\n")

    # Plot incidents per server
    plt.figure(figsize=(6, 4))
    df["Server"].value_counts().plot(kind="bar", color="skyblue")
    plt.title("Incidents per Server")
    plt.ylabel("Count")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(os.path.join(REPORTS_DIR, "incidents_per_server.png"))
    plt.close()

    # Plot incidents per issue
    plt.figure(figsize=(6, 4))
    pd.Series(issue_counts).sort_values(ascending=False).plot(kind="bar", color="salmon")
    plt.title("Incidents per Issue Type")
    plt.ylabel("Count")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(os.path.join(REPORTS_DIR, "incidents_per_issue.png"))
    plt.close()

    # Plot timeline of incidents with correct resample freq
    plt.figure(figsize=(10, 4))
    df.set_index("Time").groupby("Server").resample("1min").size().unstack(0).fillna(0).plot(kind="line")
    plt.title("Incident Timeline per Server (1-minute bins)")
    plt.ylabel("Incidents")
    plt.xlabel("Time")
    plt.legend(title="Server")
    plt.tight_layout()
    plt.savefig(os.path.join(REPORTS_DIR, "incident_timeline.png"))
    plt.close()

    # Detect spikes: sudden jumps in incidents per minute per server
    print("\nChecking for significant spikes in incidents...")
    spikes_found = False
    grouped = df.set_index("Time").groupby("Server").resample("1min").size()
    for server in df["Server"].unique():
        series = grouped[server] if server in grouped else pd.Series()
        if series.empty:
            continue
        diffs = series.diff().fillna(0)
        spike_threshold = 3  # customize this threshold as needed
        spikes = diffs[diffs >= spike_threshold]
        if not spikes.empty:
            spikes_found = True
            print(f"Significant spikes detected on {server} at times:")
            for t, val in spikes.items():
                print(f"  {t}: increase of {int(val)} incidents")

    if not spikes_found:
        print("No significant spikes detected.")
    print("Incident reports generated successfully.")

def analyze_risks():
    """Analyze risks based on metrics."""
    print("Generating risk reports...")
    if "RiskScore" not in metrics.columns:
        print("RiskScore column is missing in metrics. Skipping risk analysis.")
        return

    # Example: Generate a risk score chart
    import matplotlib.pyplot as plt
    plt.figure(figsize=(10, 6))
    metrics.plot(kind="bar", x="Server", y="RiskScore", color="red", legend=False)
    plt.title("Risk Score by Server")
    plt.ylabel("Risk Score")
    output_path = os.path.join(REPORTS_DIR, "risk_score.png")
    plt.savefig(output_path)
    plt.close()
    print(f"Risk report saved to {output_path}")

def run_analyze_logs(self):
    """Run analyze_logs.py to generate reports."""
    try:
        analyze_logs_main()  # Call the main function from analyze_logs.py
        self.append_log("[UI] Successfully ran analyze_logs.py", "system")
        self.refresh_reports_list()  # Refresh the reports list in the UI
    except Exception as e:
        self.append_log(f"[UI] Error running analyze_logs.py: {e}", "system")

# Timer to periodically run analyze_logs.py
analyze_logs_timer = QTimer()
analyze_logs_timer.timeout.connect(run_analyze_logs)
analyze_logs_timer.start(5000)  # Run every 5 seconds

def refresh_reports_list(self):
    if not self.reports_dir.exists():
        return
    files = sorted([p for p in self.reports_dir.iterdir() if p.suffix.lower() in ('.png', '.jpg', '.jpeg')],
                   key=os.path.getmtime, reverse=True)
    for p in files:
        if p.name not in self.displayed_images:  # Only add new images
            self.reports_list.addItem(p.name)
            self.displayed_images.add(p.name)  # Mark as displayed

def analyze_incidents(metrics: pd.DataFrame):
    print("Generating incident reports...")
    import matplotlib.pyplot as plt
    plt.figure(figsize=(10, 6))
    metrics.plot(kind="bar", x="Server", y="CPU", color="blue", legend=False)
    plt.title("CPU Usage by Server")
    plt.ylabel("CPU (%)")
    output_path = os.path.join(REPORTS_DIR, "cpu_usage.png")
    plt.savefig(output_path)
    plt.close()
    print(f"Incident report saved to {output_path}")

def analyze_risks(metrics: pd.DataFrame):
    """Analyze risks based on metrics."""
    print("Generating risk reports...")
    if "RiskScore" not in metrics.columns:
        print("RiskScore column is missing in metrics. Skipping risk analysis.")
        return

    # Example: Generate a risk score chart
    import matplotlib.pyplot as plt
    plt.figure(figsize=(10, 6))
    metrics.plot(kind="bar", x="Server", y="RiskScore", color="red", legend=False)
    plt.title("Risk Score by Server")
    plt.ylabel("Risk Score")
    output_path = os.path.join(REPORTS_DIR, "risk_score.png")
    plt.savefig(output_path)
    plt.close()
    print(f"Risk report saved to {output_path}")

def run_analyzer(self):
    try:
        metrics_file = self.reports_dir / "current_metrics.csv"
        print(f"Saving metrics to {metrics_file}")
        if self.last_snapshot["no_inject"] is not None:
            self.last_snapshot["no_inject"].to_csv(metrics_file, index=False)
            print(f"Metrics saved successfully.")
        else:
            print("No metrics available.")
            self.append_log("[UI] No metrics available for analysis.", "system")
            return

        print(f"Running analyzer with {metrics_file}")
        subprocess.run([sys.executable, "analyze_logs.py", str(metrics_file)], check=True)
        self.append_log("[UI] Analysis completed.", "system")
        self.refresh_reports_list()
    except subprocess.CalledProcessError as e:
        print(f"Analyzer script failed: {e}")
        self.append_log(f"[UI] Error running analyzer: {e}", "system")
    except Exception as e:
        print(f"Unexpected error: {e}")
        self.append_log(f"[UI] Unexpected error: {e}", "system")

def main():
    print("Starting analysis...")
    if len(sys.argv) > 1:
        metrics_file = sys.argv[1]
        print(f"Metrics file provided: {metrics_file}")
        if os.path.exists(metrics_file):
            metrics = pd.read_csv(metrics_file)
            print(f"Metrics loaded successfully:\n{metrics.head()}")
            analyze_incidents(metrics)
            analyze_risks(metrics)
        else:
            print(f"Metrics file '{metrics_file}' not found.")
            sys.exit(1)
    else:
        print("No metrics file provided.")
        sys.exit(1)

if __name__ == "__main__":
    main()
    print(f"\nReports and summary saved in '{REPORTS_DIR}/' folder.")
    import pandas as pd

    metrics_file = "reports/current_metrics.csv"
    metrics = pd.read_csv(metrics_file)
    print(metrics.head())

