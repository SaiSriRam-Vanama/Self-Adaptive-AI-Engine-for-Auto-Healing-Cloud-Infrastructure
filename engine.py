# engine.py
import pandas as pd
import random
import datetime
import os
import json
from collections import deque
from sklearn.ensemble import IsolationForest
from typing import List, Dict, Any
from risk_prediction import RiskPredictor
import config

def send_email_alert(server, issues):
    # placeholder - replace with real email integration
    print(f"Sending EMAIL alert for {server}: {issues}")

class AutoHealingEngine:
    """Non-injected engine — generates normal metrics and runs detection/risk."""
    def __init__(self):
        self.servers = config.SERVERS
        self.logs: List[Dict[str, Any]] = []
        self.feature_cols = ["CPU", "Memory", "Errors"]
        self.model = IsolationForest(contamination=config.CONTAMINATION, random_state=42)
        self.trained = False
        self.error_threshold = config.ERROR_THRESHOLD
        self.cooldown_seconds = config.COOLDOWN_SECONDS
        self.last_alert_time: Dict[str, Dict[str, float]] = {s: {} for s in self.servers}
        self.history: Dict[str, Dict[str, deque]] = {
            s: {col: deque(maxlen=config.HISTORY_LENGTH) for col in self.feature_cols}
            for s in self.servers
        }
        self.risk_predictors = {s: RiskPredictor(window_size=config.RISK_WINDOW_SIZE) for s in self.servers}

        os.makedirs(config.LOG_DIR, exist_ok=True)
        os.makedirs(config.REPORTS_DIR, exist_ok=True)

        self.current_cycle = 0

    def generate_metrics(self) -> pd.DataFrame:
        data = []
        for server in self.servers:
            cpu = random.randint(10, 80)  # normal-ish range
            memory = random.randint(10, 80)
            errors = round(random.uniform(0, 4), 2)
            data.append([server, cpu, memory, errors])
        return pd.DataFrame(data, columns=["Server"] + self.feature_cols)

    def _should_alert(self, server: str, issue: str) -> bool:
        now = datetime.datetime.now().timestamp()
        last = self.last_alert_time.get(server, {})
        last_ts = last.get(issue)
        if last_ts is None or (now - last_ts) >= self.cooldown_seconds:
            self.last_alert_time.setdefault(server, {})[issue] = now
            return True
        return False

    def update_history(self, df: pd.DataFrame):
        for _, row in df.iterrows():
            server = row["Server"]
            for col in self.feature_cols:
                self.history[server][col].append(row[col])
            self.risk_predictors[server].update_metrics(row["CPU"], row["Memory"], row["Errors"])

    def predict_risks(self) -> List[Dict[str, Any]]:
        risks = []
        for server in self.servers:
            prediction = self.risk_predictors[server].predict_risk()
            if prediction["risk_level"] in ["High", "Medium"]:
                issues = []
                if prediction["risk_score"] > 70:
                    issues.append(f"High Risk Score ({prediction['risk_score']:.1f})")
                elif prediction["risk_score"] > 40:
                    issues.append(f"Medium Risk Score ({prediction['risk_score']:.1f})")

                log_entry = {
                    "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "server": server,
                    "risk_score": prediction["risk_score"],
                    "cpu_trend": prediction["cpu_trend"],
                    "risk_level": prediction["risk_level"],
                    "issues": issues,
                }
                with open(os.path.join(config.LOG_DIR, "risk_warnings.jsonl"), "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry) + "\n")

                risks.append(log_entry)
        return risks

    def detect_anomalies(self, df: pd.DataFrame) -> pd.DataFrame:
        features = df[self.feature_cols]
        # Fit or retrain (simple approach)
        if not self.trained:
            self.model.fit(features)
            self.trained = True
        else:
            self.model.fit(features)

        df = df.copy()
        # Ensure column names passed to avoid sklearn warnings
        df["Anomaly"] = self.model.predict(features)

        for _, row in df.iterrows():
            if row["Anomaly"] == -1:
                issues = []
                if row["CPU"] > 80:
                    issues.append("High CPU Usage")
                if row["Memory"] > 80:
                    issues.append("High Memory Usage")
                if row["Errors"] > self.error_threshold:
                    issues.append("High Error Rate")

                unique_issues = list(dict.fromkeys(issues))
                if unique_issues:
                    to_alert = []
                    for issue in unique_issues:
                        if self._should_alert(row["Server"], issue):
                            to_alert.append(issue)
                    if to_alert:
                        self.healing_action(row["Server"], to_alert)

        return df

    def healing_action(self, server: str, issues: List[str]):
        actions = []
        for issue in issues:
            if "CPU" in issue:
                actions.append("Scaled CPU resources")
            if "Memory" in issue:
                actions.append("Restarted memory-intensive service")
            if "Error" in issue:
                actions.append("Restarted faulty process")

        log_entry = {
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "server": server,
            "issues": issues,
            "actions": actions
        }
        self.logs.append(log_entry)

        print(f"[{log_entry['time']}] ALERT on {server}: {issues}")
        for act in actions:
            print(f"  -> {act}")
        print("-" * 50)

        with open(os.path.join(config.LOG_DIR, "incidents.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")

        send_email_alert(server, issues)

    def plot_metrics(self, df: pd.DataFrame, save_png: bool = True, cycle_index: int = 0):
        # Matplotlib snapshot (kept for reports, not used by UI's live charts)
        import matplotlib.pyplot as plt
        plt.figure(figsize=(10, 4))
        for col in ["CPU", "Memory"]:
            plt.plot(df["Server"], df[col], marker='o', label=col)
        plt.title(f"Server Metrics Cycle {cycle_index}")
        plt.xlabel("Server")
        plt.ylabel("Usage (%)")
        plt.ylim(0, 100)
        plt.legend()
        plt.tight_layout()
        if save_png:
            plt.savefig(os.path.join(config.REPORTS_DIR, f"metrics_cycle_{cycle_index}.png"))
        plt.close()
