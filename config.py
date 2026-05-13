# Configuration for AutoHealingEngine and RiskPredictor

SERVERS = ["server-1", "server-2", "server-3", "server-4"]

CONTAMINATION = 0.15  # anomaly sensitivity
ERROR_THRESHOLD = 3.0  # error rate threshold for alerts
COOLDOWN_SECONDS = 5   # cooldown between alerts for same issue

HISTORY_LENGTH = 10    # number of cycles history to keep for risk prediction
RISK_WINDOW_SIZE = 5   # window size for moving averages

LOG_DIR = "logs"
REPORTS_DIR = "reports"

INJECT_FAILURES = True  # Flag to enable/disable failure injection
