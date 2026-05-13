# auto_healing_ui.py — Full PyQt5 UI with "Generate Reports" button enabled after stop
import sys
import os
from pathlib import Path
import threading
import time
from collections import deque
from typing import List, Dict, Any
import subprocess  # <-- Import subprocess here

# Ensure project root is importable (adjust if your layout differs)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ---- PyQt5 ----
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
    QPlainTextEdit, QLabel, QHBoxLayout, QComboBox, QSplitter, QListWidget, QListWidgetItem,
    QFrame, QSlider, QFileDialog, QMessageBox, QSizePolicy
)
from PyQt5.QtCore import pyqtSignal, QObject, Qt, QTimer
from PyQt5.QtGui import QPixmap

# ---- plotting ----
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import pyqtgraph as pg
import pandas as pd
import numpy as np

# ---- Engines & config ----
try:
    from engine import AutoHealingEngine as AutoHealingEngineNoInject
    from engine_inject import AutoHealingEngineInjected as AutoHealingEngineInject
    import config
    ENGINES_OK = True
except Exception as e:
    ENGINES_OK = False
    _engine_import_error = str(e)

# ---- Analyzer (optional) ----
try:
    import ui.analyze_logs as analyze_logs  # must expose analyze_incidents() and analyze_risks()
    ANALYZER_OK = True
except Exception as e:
    ANALYZER_OK = False
    _analyzer_import_error = str(e)

# Ensure directories exist
if ENGINES_OK:
    os.makedirs(config.LOG_DIR, exist_ok=True)
    os.makedirs(config.REPORTS_DIR, exist_ok=True)
else:
    os.makedirs("logs", exist_ok=True)
    os.makedirs("reports", exist_ok=True)

# Log file paths (legacy pipe-delimited for analyzer compatibility)
INCIDENTS_LOG_PATH = os.path.join(config.LOG_DIR if ENGINES_OK else "logs", "incidents.log")
RISK_LOG_PATH = os.path.join(config.LOG_DIR if ENGINES_OK else "logs", "risk_warnings.log")

# --- Worker Signals ---
class WorkerSignals(QObject):
    metrics_updated = pyqtSignal(object, str)  # dataframe, mode
    log_updated = pyqtSignal(str, str)         # text, tag

# --- Snapshot Matplotlib canvas ---
class SnapshotCanvas(FigureCanvas):
    def __init__(self, parent=None, width=6, height=3, dpi=100, mode="no_inject"):
        fig = Figure(figsize=(width, height), dpi=dpi)
        self.ax = fig.add_subplot(111)
        self.mode = mode
        super().__init__(fig)
        self.setParent(parent)
        fig.tight_layout()

    def plot_snapshot(self, df: pd.DataFrame):
        self.ax.clear()
        try:
            servers = list(df["Server"])
            cpu = list(df["CPU"])
            mem = list(df["Memory"])
            x = range(len(servers))
            width = 0.35
            
            # Use different colors based on mode
            if self.mode == "no_inject":
                cpu_color = "#4CAF50"  # Green
                mem_color = "#81C784"  # Light green
            else:
                cpu_color = "#F44336"  # Red
                mem_color = "#E57373"  # Light red
                
            self.ax.bar([i - width/2 for i in x], cpu, width=width, label="CPU (%)", color=cpu_color)
            self.ax.bar([i + width/2 for i in x], mem, width=width, label="Memory (%)", color=mem_color)
            self.ax.set_xticks(list(x))
            self.ax.set_xticklabels(servers, rotation=20)
            self.ax.set_ylim(0, 110)
            self.ax.set_ylabel("Usage (%)")
            title_color = "#4CAF50" if self.mode == "no_inject" else "#F44336"
            self.ax.set_title(f"Snapshot: CPU & Memory ({self.mode.replace('_', ' ').title()})", color=title_color)
            self.ax.legend()
        except Exception:
            self.ax.text(0.5, 0.5, "No data", ha='center')
        self.draw()

# --- Monitor Thread: pulls metrics & writes logs in analyzer-compatible format ---
class MonitorThread(threading.Thread):
    def __init__(self, engine, signals, interval=1.0, mode="no_inject"):
        super().__init__(daemon=True)
        self.engine = engine
        self.signals = signals
        self.interval = interval
        self.mode = mode
        self.running = False
        self._last_written_idx = 0

    def _write_incident_line(self, entry: Dict[str, Any]):
        ts = entry.get("time", time.strftime("%Y-%m-%d %H:%M:%S"))
        server = entry.get("server", "?")
        issues = entry.get("issues", [])
        actions = entry.get("actions", [])
        # Write as pipe-delimited plain text (analyze_logs.py accepts this fallback)
        line = f"{ts}|{server}|{issues}|{actions}\n"
        with open(INCIDENTS_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)

    def _write_risks(self, risks: List[Dict[str, Any]]):
        for r in risks:
            ts = r.get("time", time.strftime("%Y-%m-%d %H:%M:%S"))
            server = r.get("server", "?")
            issues = r.get("issues", [])
            issues_str = ", ".join(issues) if isinstance(issues, list) else str(issues)
            line = f"{ts}|{server}|{issues_str}\n"
            with open(RISK_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line)

    def run(self):
        self.running = True
        if hasattr(self.engine, "current_cycle"):
            self.engine.current_cycle = 0

        while self.running:
            try:
                if hasattr(self.engine, "current_cycle"):
                    self.engine.current_cycle += 1

                df = self.engine.generate_metrics()
                self.engine.update_history(df)
                df = self.engine.detect_anomalies(df)
                risks = self.engine.predict_risks()

                # emit metrics snapshot
                self.signals.metrics_updated.emit(df, self.mode)

                # write & emit new healing logs
                logs = getattr(self.engine, "logs", [])
                if logs and self._last_written_idx < len(logs):
                    new_entries = logs[self._last_written_idx:]
                    self._last_written_idx = len(logs)
                    for entry in new_entries:
                        self.signals.log_updated.emit(
                            f"[ALERT] {entry.get('server', '?')}: {', '.join(entry.get('issues', []))}",
                            self.mode
                        )
                        # persist to incidents log
                        try:
                            self._write_incident_line(entry)
                        except Exception:
                            pass

                # emit risk warnings + persist
                if risks:
                    for r in risks:
                        self.signals.log_updated.emit(
                            f"[RISK-{r.get('risk_level','?')}] {r.get('server','?')}: "
                            f"{', '.join(r.get('issues', [])) if r.get('issues') else 'No details'}",
                            self.mode
                        )
                    try:
                        self._write_risks(risks)
                    except Exception:
                        pass

            except Exception as e:
                self.signals.log_updated.emit(f"[Thread {self.mode}] Exception: {e}", "system")

            time.sleep(self.interval)

    def stop(self):
        self.running = False

# --- Image Popup ---
class ImagePopup(QWidget):
    def __init__(self, image_path):
        super().__init__()
        self.setWindowTitle(os.path.basename(image_path))
        self.resize(900, 640)
        layout = QVBoxLayout()
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.image_label)
        self.setLayout(layout)
        self._set_image(image_path)

    def _set_image(self, path):
        pix = QPixmap(path)
        if pix.isNull():
            self.image_label.setText("Cannot preview image")
            return
        self._pix = pix
        self._rescale()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self):
        if hasattr(self, "_pix"):
            scaled = self._pix.scaled(self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.image_label.setPixmap(scaled)

# --- Main UI ---
class AutoHealingUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Auto-Healing AI — Dual Engine Live Dashboard")
        self.setGeometry(100, 50, 1500, 920)

        if not ENGINES_OK:
            self._fatal_boot_error(_engine_import_error)

        self.signals = WorkerSignals()
        self.signals.metrics_updated.connect(self.on_metrics_update)
        self.signals.log_updated.connect(self.on_log_update)

        # engines/threads
        self.engine_no = None
        self.engine_inj = None
        self.thread_no = None
        self.thread_inj = None

        # plotting buffers
        self.max_points = 300
        self.buffers = {"no_inject": {}, "inject": {}}
        self.curves = {"no_inject": {}, "inject": {}}
        self.last_snapshot = {"no_inject": None, "inject": None}

        # reports directory
        self.reports_dir = Path("reports")

        # seen files for report list
        self._list_seen_files = set()

        # analysis lock
        self._analysis_running = False

        self._build_ui()

        # UI refresh timer (graph updates)
        self.ui_timer = QTimer(self)
        self.ui_timer.setInterval(1000 // 60)  # 60 FPS for smoothness
        self.ui_timer.timeout.connect(self.refresh_graphs)
        self.ui_timer.start()

        # Refresh reports list regularly
        self.report_timer = QTimer(self)
        self.report_timer.timeout.connect(self.refresh_reports_list)
        self.report_timer.start(3000)

    # --- UI build ---
    def _build_ui(self):
        main_layout = QVBoxLayout()

        # Header
        header = QLabel("AUTO-HEALING AI — LIVE DASHBOARD")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("font-size:20pt; font-weight:bold; padding:8px;")
        main_layout.addWidget(header)

        # Controls
        controls = QHBoxLayout()
        self.mode_selector = QComboBox()
        self.mode_selector.addItems(["Single Mode", "Dual View"])
        controls.addWidget(QLabel("Display Mode:"))
        controls.addWidget(self.mode_selector)

        self.single_selector = QComboBox()
        self.single_selector.addItems(["No Injection", "Injected"])
        controls.addWidget(QLabel("Single:"))
        controls.addWidget(self.single_selector)

        self.start_no_btn = QPushButton("Start No Injection")
        self.start_no_btn.clicked.connect(self.start_no)
        controls.addWidget(self.start_no_btn)
        self.stop_no_btn = QPushButton("Stop No Injection")
        self.stop_no_btn.clicked.connect(self.stop_no)
        self.stop_no_btn.setEnabled(False)
        controls.addWidget(self.stop_no_btn)

        self.start_inj_btn = QPushButton("Start Injected")
        self.start_inj_btn.clicked.connect(self.start_inj)
        controls.addWidget(self.start_inj_btn)
        self.stop_inj_btn = QPushButton("Stop Injected")
        self.stop_inj_btn.clicked.connect(self.stop_inj)
        self.stop_inj_btn.setEnabled(False)
        controls.addWidget(self.stop_inj_btn)

        # Interval slider (ms)
        self.interval_slider = QSlider(Qt.Horizontal)
        self.interval_slider.setRange(50, 1000)  # 50 ms to 1000 ms
        self.interval_slider.setValue(200)
        self.interval_slider.valueChanged.connect(self.on_interval_change)
        controls.addWidget(QLabel("Interval (ms):"))
        controls.addWidget(self.interval_slider)
        self.interval_label = QLabel("200 ms")
        controls.addWidget(self.interval_label)

        # Manual "Run Analysis Now" button (hidden until engines stopped)
        self.generate_reports_btn = QPushButton("Generate Reports")
        self.generate_reports_btn.clicked.connect(self.generate_reports)
        self.generate_reports_btn.setEnabled(False)  # disabled initially
        controls.addWidget(self.generate_reports_btn)

        # Report generation status
        self.report_status_label = QLabel("Reports: Ready")
        self.report_status_label.setStyleSheet("padding: 4px; border: 1px solid #ccc; background: #f0f0f0;")
        controls.addWidget(self.report_status_label)

        # Compare graphs button
        self.compare_graphs_btn = QPushButton("Compare Graphs")
        self.compare_graphs_btn.clicked.connect(self.on_compare_graphs_clicked)
        controls.addWidget(self.compare_graphs_btn)

        # Export comparison data button
        self.export_comparison_btn = QPushButton("Export Comparison")
        self.export_comparison_btn.clicked.connect(self.on_export_comparison_clicked)
        controls.addWidget(self.export_comparison_btn)

        # Open reports folder
        self.open_reports_btn = QPushButton("Open Reports Folder")
        self.open_reports_btn.clicked.connect(self.open_reports_folder)
        controls.addWidget(self.open_reports_btn)

        main_layout.addLayout(controls)

        # Splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left panel (tables + snapshots)
        left = QFrame()
        left_layout = QVBoxLayout()
        left.setLayout(left_layout)

        # Tables
        self.table_no = QTableWidget(0, 4)
        self.table_no.setHorizontalHeaderLabels(["Server", "CPU (%)", "Memory (%)", "Errors"])
        self.table_inj = QTableWidget(0, 4)
        self.table_inj.setHorizontalHeaderLabels(["Server", "CPU (%)", "Memory (%)", "Errors"])

        left_layout.addWidget(QLabel("No Injection Metrics"))
        left_layout.addWidget(self.table_no)
        left_layout.addWidget(QLabel("Injected Metrics"))
        left_layout.addWidget(self.table_inj)

        # Snapshots
        snapshots_layout = QHBoxLayout()
        self.snapshot_no = SnapshotCanvas(self, width=3, height=3, dpi=100, mode="no_inject")
        self.snapshot_inj = SnapshotCanvas(self, width=3, height=3, dpi=100, mode="inject")
        snapshots_layout.addWidget(self.snapshot_no)
        snapshots_layout.addWidget(self.snapshot_inj)
        left_layout.addLayout(snapshots_layout)

        splitter.addWidget(left)

        # Right panel (graphs + logs + reports)
        right = QFrame()
        right_layout = QVBoxLayout()
        right.setLayout(right_layout)

        # Live charts (pyqtgraph)
        pg.setConfigOptions(antialias=True)
        self.pg_no = pg.PlotWidget(title="🟢 No Injection — CPU (time)")
        self.pg_no.setBackground('w')
        self.pg_no.showGrid(x=True, y=True, alpha=0.3)
        self.pg_no.addLegend()
        self.pg_no.setMinimumHeight(200)  # Set minimum height for better visibility
        self.pg_no.setLabel('left', 'CPU Usage (%)')
        self.pg_no.setLabel('bottom', 'Time (cycles)')
        self.pg_no.setYRange(0, 100)

        self.pg_inj = pg.PlotWidget(title="🔴 Injected — CPU (time)")
        self.pg_inj.setBackground('w')
        self.pg_inj.showGrid(x=True, y=True, alpha=0.3)
        self.pg_inj.addLegend()
        self.pg_inj.setMinimumHeight(200)  # Set minimum height for better visibility
        self.pg_inj.setLabel('left', 'CPU Usage (%)')
        self.pg_inj.setLabel('bottom', 'Time (cycles)')
        self.pg_inj.setYRange(0, 100)

        right_layout.addWidget(self.pg_no, 3)  # Increased stretch factor from 2 to 3
        right_layout.addWidget(self.pg_inj, 3)  # Increased stretch factor from 2 to 3

        # Logs — use QPlainTextEdit for setMaximumBlockCount
        self.log_area = QPlainTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumBlockCount(2000)
        right_layout.addWidget(QLabel("Logs"))
        right_layout.addWidget(self.log_area, 1)

        # Reports view
        self.reports_list = QListWidget()
        self.reports_list.setMaximumHeight(160)
        # FIX: connect to the existing handler method
        self.reports_list.itemClicked.connect(self.on_report_selected)
        self.report_preview = QLabel("Report preview")
        self.report_preview.setAlignment(Qt.AlignCenter)
        self.report_preview.setMinimumHeight(260)
        right_layout.addWidget(QLabel("Reports & Analysis Files"))
        right_layout.addWidget(self.reports_list)
        right_layout.addWidget(self.report_preview)

        # Comparison status
        self.comparison_label = QLabel("Comparison: Waiting for data...")
        self.comparison_label.setAlignment(Qt.AlignCenter)
        self.comparison_label.setStyleSheet("padding: 8px; border: 1px solid #ccc; background: #f5f5f5;")
        self.comparison_label.setMaximumHeight(80)
        right_layout.addWidget(QLabel("Real-time Comparison"))
        right_layout.addWidget(self.comparison_label)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

    # --- control callbacks ---
    def on_interval_change(self, val):
        ms = val
        self.interval_label.setText(f"{ms} ms")
        seconds = ms / 1000.0
        if self.thread_no and self.thread_no.is_alive():
            self.thread_no.interval = seconds
        if self.thread_inj and self.thread_inj.is_alive():
            self.thread_inj.interval = seconds

    def start_no(self):
        if self.thread_no and self.thread_no.is_alive():
            self.append_log("[UI] No-Injection already running", "system")
            return
        self.engine_no = AutoHealingEngineNoInject()
        self._init_buffers("no_inject", self.engine_no.servers)
        interval = self.interval_slider.value() / 1000.0
        self.thread_no = MonitorThread(self.engine_no, self.signals, interval=interval, mode="no_inject")
        self.thread_no.start()
        self.start_no_btn.setEnabled(False)
        self.stop_no_btn.setEnabled(True)
        self.append_log("[UI] Started No-Injection engine", "system")
        # disable reports button while engine runs
        self.generate_reports_btn.setEnabled(False)

    def stop_no(self):
        if self.thread_no:
            self.thread_no.stop()
            self.thread_no.join(timeout=1)
            self.thread_no = None
            self.start_no_btn.setEnabled(True)
            self.stop_no_btn.setEnabled(False)
            self.append_log("[UI] Stopped No-Injection engine", "system")
            # Check whether both engines stopped to enable reports and possibly run analysis
            self._maybe_enable_reports()

    def start_inj(self):
        if self.thread_inj and self.thread_inj.is_alive():
            self.append_log("[UI] Injected already running", "system")
            return
        self.engine_inj = AutoHealingEngineInject()
        self._init_buffers("inject", self.engine_inj.servers)
        interval = self.interval_slider.value() / 1000.0
        self.thread_inj = MonitorThread(self.engine_inj, self.signals, interval=interval, mode="inject")
        self.thread_inj.start()
        self.start_inj_btn.setEnabled(False)
        self.stop_inj_btn.setEnabled(True)
        self.append_log("[UI] Started Injected engine", "system")
        # disable reports button while engine runs
        self.generate_reports_btn.setEnabled(False)

    def stop_inj(self):
        if self.thread_inj:
            self.thread_inj.stop()
            self.thread_inj.join(timeout=1)
            self.thread_inj = None
            self.start_inj_btn.setEnabled(True)
            self.stop_inj_btn.setEnabled(False)
            self.append_log("[UI] Stopped Injected engine", "system")
            # After stopping injection, allow reports button and auto-run analysis
            self._maybe_enable_reports()

    def _maybe_enable_reports(self):
        # Enable reports button only when both engine threads are not running
        no_running = not (self.thread_no and self.thread_no.is_alive())
        inj_running = not (self.thread_inj and self.thread_inj.is_alive())
        if no_running and inj_running:
            # Always enable reports since we have built-in generation
            self.generate_reports_btn.setEnabled(True)
            self.append_log("[UI] Reports available — click 'Generate Reports' to run analysis", "system")
            # Automatically start analysis in background once after both stopped
            self._start_analysis_background(auto_trigger=True)
        else:
            self.generate_reports_btn.setEnabled(False)

    def _init_buffers(self, mode, servers):
        for i, s in enumerate(servers):
            self.buffers[mode].setdefault(s, deque(maxlen=self.max_points))
            if s not in self.curves[mode]:
                # Use green for no-injection, red for injected with different line styles
                if mode == "no_inject":
                    color = "#4CAF50"  # Green color
                    line_style = Qt.SolidLine
                    curve = self.pg_no.plot([], pen=pg.mkPen(color=color, width=3, style=line_style), name=s)
                else:
                    color = "#F44336"  # Red color
                    line_style = Qt.DashLine  # Dashed line for injected
                    curve = self.pg_inj.plot([], pen=pg.mkPen(color=color, width=3, style=line_style), name=s)
                self.curves[mode][s] = curve

    def compare_graphs(self):
        """Compare the two graphs to check for differences."""
        try:
            if not self.buffers["no_inject"] or not self.buffers["inject"]:
                return "Cannot compare: One or both engines not running"
            
            differences = []
            all_servers = set(self.buffers["no_inject"].keys()) | set(self.buffers["inject"].keys())
            
            for server in all_servers:
                no_inj_data = list(self.buffers["no_inject"].get(server, []))
                inj_data = list(self.buffers["inject"].get(server, []))
                
                if not no_inj_data and not inj_data:
                    continue
                    
                if not no_inj_data:
                    differences.append(f"{server}: No data in no-injection")
                    continue
                if not inj_data:
                    differences.append(f"{server}: No data in injected")
                    continue
                
                # Compare the latest values
                if len(no_inj_data) > 0 and len(inj_data) > 0:
                    no_inj_latest = no_inj_data[-1]
                    inj_latest = inj_data[-1]
                    diff = abs(no_inj_latest - inj_latest)
                    
                    if diff > 5.0:  # Threshold of 5% difference
                        differences.append(f"{server}: CPU diff {diff:.1f}% (No-inj: {no_inj_latest:.1f}%, Inj: {inj_latest:.1f}%)")
                    
                    # Compare data lengths
                    if len(no_inj_data) != len(inj_data):
                        differences.append(f"{server}: Data length diff (No-inj: {len(no_inj_data)}, Inj: {len(inj_data)})")
            
            if differences:
                return f"Found {len(differences)} differences:\n" + "\n".join(differences)
            else:
                return "No significant differences found between graphs"
                
        except Exception as e:
            return f"Error comparing graphs: {e}"

    # --- signals ---
    def on_metrics_update(self, df, mode):
        self.last_snapshot[mode] = df.copy()
        if mode == "no_inject":
            self.snapshot_no.plot_snapshot(df)
        elif mode == "inject":
            self.snapshot_inj.plot_snapshot(df)

        try:
            if mode == "no_inject":
                self._update_table(self.table_no, df)
            elif mode == "inject":
                self._update_table(self.table_inj, df)
        except Exception as e:
            self.append_log(f"[UI] Table update error: {e}", "system")

        for _, row in df.iterrows():
            srv = row["Server"]
            cpu = float(row["CPU"])
            self.buffers[mode].setdefault(srv, deque(maxlen=self.max_points)).append(cpu)

    def on_log_update(self, text, tag):
        self.append_log(text, tag)

    def append_log(self, text, tag="system"):
        colors = {"inject": "#F44336", "no_inject": "#4CAF50", "system": "#212121"}  # Red for injected, Green for no-injection
        color = colors.get(tag, "#212121")
        timestamp = time.strftime("%H:%M:%S")
        # QPlainTextEdit does not have appendHtml; we keep rich text by converting to plain text with tags
        # but we can include simple markers — keep previous behavior but as plain.
        try:
            # prefer appendHtml if available, but QPlainTextEdit doesn't have it.
            # So we append a plain line with color tags stripped in the plain control.
            self.log_area.appendPlainText(f"[{timestamp}] {text}")
        except Exception:
            self.log_area.appendPlainText(f"[{timestamp}] {text}")

    def _update_table(self, table, df):
        table.setRowCount(len(df))
        for i, (_, row) in enumerate(df.iterrows()):
            table.setItem(i, 0, QTableWidgetItem(str(row["Server"])))
            table.setItem(i, 1, QTableWidgetItem(str(row["CPU"])))
            table.setItem(i, 2, QTableWidgetItem(str(row["Memory"])))
            table.setItem(i, 3, QTableWidgetItem(str(row["Errors"])))

    def refresh_graphs(self):
        try:
            for mode in ("no_inject", "inject"):
                for srv, dq in self.buffers[mode].items():
                    curve = self.curves[mode].get(srv)
                    if curve:
                        y = list(dq)
                        x = list(range(len(y)))
                        curve.setData(x, y)
            
            # Update comparison label
            self._update_comparison_label()
        except Exception:
            pass

    def _update_comparison_label(self):
        """Update the comparison label with current differences."""
        try:
            if not self.buffers["no_inject"] or not self.buffers["inject"]:
                self.comparison_label.setText("Comparison: Waiting for both engines to start...")
                return
            
            # Get latest values for comparison
            differences = []
            all_servers = set(self.buffers["no_inject"].keys()) | set(self.buffers["inject"].keys())
            
            for server in all_servers:
                no_inj_data = list(self.buffers["no_inject"].get(server, []))
                inj_data = list(self.buffers["inject"].get(server, []))
                
                if len(no_inj_data) > 0 and len(inj_data) > 0:
                    no_inj_latest = no_inj_data[-1]
                    inj_latest = inj_data[-1]
                    diff = abs(no_inj_latest - inj_latest)
                    
                    if diff > 2.0:  # Lower threshold for real-time display
                        differences.append(f"{server}: {diff:.1f}%")
            
            if differences:
                self.comparison_label.setText(f"⚠️ Differences detected: {', '.join(differences[:3])}")
                self.comparison_label.setStyleSheet("padding: 8px; border: 1px solid #ff9800; background: #fff3e0; color: #e65100;")
            else:
                self.comparison_label.setText("✅ No significant differences detected")
                self.comparison_label.setStyleSheet("padding: 8px; border: 1px solid #4caf50; background: #e8f5e8; color: #2e7d32;")
                
        except Exception as e:
            self.comparison_label.setText(f"Comparison error: {e}")
            self.comparison_label.setStyleSheet("padding: 8px; border: 1px solid #f44336; background: #ffebee; color: #c62828;")

    # --- Reports handling ---
    def refresh_reports_list(self):
        print("Refreshing reports list...")
        if not self.reports_dir.exists():
            print("Reports directory does not exist.")
            return
        
        # Clear the list first
        self.reports_list.clear()
        self._list_seen_files.clear()
        
        # Find all report files
        all_files = []
        
        # Text reports
        text_reports = list(self.reports_dir.glob("auto_healing_report_*.txt"))
        for report in text_reports:
            all_files.append((report, "📄 Report"))
        
        # Metrics files
        metrics_files = list(self.reports_dir.glob("metrics_*.csv"))
        for metrics in metrics_files:
            all_files.append((metrics, "📊 Metrics"))
        
        # Comparison files
        comparison_files = list(self.reports_dir.glob("comparison_*.csv"))
        for comp in comparison_files:
            all_files.append((comp, "📈 Comparison"))
        
        # Image reports (legacy)
        images = list(self.reports_dir.glob("*.png"))
        for img in images:
            all_files.append((img, "🖼️ Chart"))
        
        # Sort by modification time (newest first)
        all_files.sort(key=lambda x: x[0].stat().st_mtime, reverse=True)
        
        print(f"Found {len(all_files)} report files.")
        
        for file_path, file_type in all_files:
            if file_path.name not in self._list_seen_files:
                # Create a more informative display
                timestamp = time.strftime("%H:%M:%S", time.localtime(file_path.stat().st_mtime))
                display_text = f"{file_type} {file_path.name} ({timestamp})"
                
                item = QListWidgetItem(display_text)
                item.setData(Qt.UserRole, str(file_path))  # Store full path
                self.reports_list.addItem(item)
                self._list_seen_files.add(file_path.name)

    def display_report(self, item):
        # Get the file path from the item data
        file_path_str = item.data(Qt.UserRole)
        if not file_path_str:
            # Fallback to old method for backward compatibility
            file_path = self.reports_dir / item.text()
        else:
            file_path = Path(file_path_str)
        
        if not file_path.exists():
            self.report_preview.setText("File not found")
            return
        
        # Handle different file types
        if file_path.suffix.lower() == '.txt':
            # Text report - show content
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                # Truncate if too long
                if len(content) > 1000:
                    content = content[:1000] + "\n\n... (truncated)"
                self.report_preview.setText(content)
                self.report_preview.setWordWrap(True)
            except Exception as e:
                self.report_preview.setText(f"Error reading file: {e}")
        
        elif file_path.suffix.lower() == '.csv':
            # CSV file - show preview
            try:
                import pandas as pd
                df = pd.read_csv(file_path)
                preview = f"CSV File: {file_path.name}\n\n"
                preview += f"Shape: {df.shape[0]} rows × {df.shape[1]} columns\n\n"
                preview += "Columns:\n"
                for col in df.columns:
                    preview += f"• {col}\n"
                preview += f"\nFirst 3 rows:\n{df.head(3).to_string()}"
                self.report_preview.setText(preview)
                self.report_preview.setWordWrap(True)
            except Exception as e:
                self.report_preview.setText(f"Error reading CSV: {e}")
        
        elif file_path.suffix.lower() in ['.png', '.jpg', '.jpeg']:
            # Image file - show image
            pix = QPixmap(str(file_path))
            if pix.isNull():
                self.report_preview.setText("Cannot preview image")
            else:
                scaled = pix.scaled(self.report_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.report_preview.setPixmap(scaled)
        
        else:
            # Unknown file type
            self.report_preview.setText(f"Unknown file type: {file_path.suffix}")
        
        # Show popup for all file types
        if file_path.suffix.lower() in ['.png', '.jpg', '.jpeg']:
            popup = ImagePopup(str(file_path))
        else:
            # For text/CSV files, create a text popup
            popup = self._create_text_popup(file_path)
        
        popup.show()
        if not hasattr(self, "_popups"):
            self._popups = []
        self._popups.append(popup)

    def _create_text_popup(self, file_path):
        """Create a text popup for non-image files."""
        popup = QWidget()
        popup.setWindowTitle(f"Report: {file_path.name}")
        popup.resize(800, 600)
        
        layout = QVBoxLayout()
        
        # Title
        title = QLabel(f"📄 {file_path.name}")
        title.setStyleSheet("font-size: 16pt; font-weight: bold; padding: 10px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Content
        text_area = QPlainTextEdit()
        text_area.setReadOnly(True)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            text_area.setPlainText(content)
        except Exception as e:
            text_area.setPlainText(f"Error reading file: {e}")
        
        layout.addWidget(text_area)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(popup.close)
        layout.addWidget(close_btn)
        
        popup.setLayout(layout)
        return popup

    def on_report_selected(self, item):
        """Compatibility wrapper for QListWidget.itemClicked signal."""
        # simply delegate to display_report
        self.display_report(item)

    def open_reports_folder(self):
        folder = str(self.reports_dir.resolve())
        if sys.platform.startswith("win"):
            os.startfile(folder)
        elif sys.platform == "darwin":
            os.system(f'open "{folder}"')
        else:
            os.system(f'xdg-open "{folder}"')

    def on_generate_reports_clicked(self):
        # Manual trigger for analysis (background)
        if not ANALYZER_OK:
            QMessageBox.warning(self, "Analyzer Missing", f"analyze_logs import failed: {_analyzer_import_error}")
            return
        if self._analysis_running:
            self.append_log("[UI] Analysis already running", "system")
            return

        self.generate_reports()

    def on_compare_graphs_clicked(self):
        """Handle Compare Graphs button click."""
        comparison_result = self.compare_graphs()
        QMessageBox.information(self, "Graph Comparison", comparison_result)
        self.append_log(f"[UI] Graph comparison: {comparison_result}", "system")

    def on_export_comparison_clicked(self):
        """Handle Export Comparison button click."""
        comparison_result = self.compare_graphs()
        if "Cannot compare: One or both engines not running" in comparison_result:
            QMessageBox.warning(self, "No Data to Export", "No data available to export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Export Comparison Data", "comparison_data.csv", "CSV Files (*.csv)")
        if file_path:
            try:
                with open(file_path, "w", newline="") as f:
                    f.write("Server,No_Injection_CPU,Injected_CPU,Difference\n")
                    all_servers = set(self.buffers["no_inject"].keys()) | set(self.buffers["inject"].keys())
                    for server in all_servers:
                        no_inj_data = list(self.buffers["no_inject"].get(server, []))
                        inj_data = list(self.buffers["inject"].get(server, []))
                        if len(no_inj_data) > 0 and len(inj_data) > 0:
                            no_inj_latest = no_inj_data[-1]
                            inj_latest = inj_data[-1]
                            diff = abs(no_inj_latest - inj_latest)
                            f.write(f"{server},{no_inj_latest:.1f},{inj_latest:.1f},{diff:.1f}\n")
                QMessageBox.information(self, "Export Successful", f"Comparison data exported to {file_path}")
                self.append_log(f"[UI] Comparison data exported to {file_path}", "system")
            except Exception as e:
                QMessageBox.critical(self, "Export Failed", f"Failed to export comparison data: {e}")
                self.append_log(f"[UI] Error exporting comparison data: {e}", "system")

    def generate_reports(self):
        """Run analysis and refresh reports."""
        self.append_log("[UI] Running analysis (background)...", "system")
        self.report_status_label.setText("Reports: Generating...")
        self.report_status_label.setStyleSheet("padding: 4px; border: 1px solid #ff9800; background: #fff3e0; color: #e65100;")
        QTimer.singleShot(100, self.run_analyzer)

    def run_analyzer(self):
        """Generate reports based on current metrics and logs."""
        try:
            self._analysis_running = True
            self.append_log("[UI] Generating reports from current data...", "system")
            
            # Create comprehensive report
            report_data = self._generate_comprehensive_report()
            
            # Save report to file
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            report_file = self.reports_dir / f"auto_healing_report_{timestamp}.txt"
            
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(report_data)
            
            # Also save current metrics as CSV
            metrics_file = self.reports_dir / f"metrics_{timestamp}.csv"
            if self.last_snapshot["no_inject"] is not None:
                df = self.last_snapshot["no_inject"].copy()
                if "RiskScore" not in df.columns:
                    df["RiskScore"] = (df["CPU"] * 0.5) + (df["Memory"] * 0.3) - (df["Errors"] * 10)
                df.to_csv(metrics_file, index=False)
            
            # Create comparison report if both engines have data
            if self.last_snapshot["no_inject"] is not None and self.last_snapshot["inject"] is not None:
                comparison_file = self.reports_dir / f"comparison_{timestamp}.csv"
                self._export_comparison_data(comparison_file)
            
            # Generate charts
            self._generate_charts(timestamp)
            
            self.append_log(f"[UI] Reports generated successfully: {report_file}", "system")
            QMessageBox.information(self, "Reports Generated", 
                                  f"Reports generated successfully!\n\nFiles created:\n• {report_file.name}\n• {metrics_file.name}")
            
            # Refresh reports list
            self.refresh_reports_list()
            
            # Update status
            self.report_status_label.setText("Reports: Complete")
            self.report_status_label.setStyleSheet("padding: 4px; border: 1px solid #4caf50; background: #e8f5e8; color: #2e7d32;")
            
        except Exception as e:
            error_msg = f"Error generating reports: {e}"
            self.append_log(f"[UI] {error_msg}", "system")
            QMessageBox.critical(self, "Report Generation Failed", error_msg)
            
            # Update status to error
            self.report_status_label.setText("Reports: Error")
            self.report_status_label.setStyleSheet("padding: 4px; border: 1px solid #f44336; background: #ffebee; color: #c62828;")
        finally:
            self._analysis_running = False

    def _generate_comprehensive_report(self):
        """Generate a comprehensive report from current data."""
        report_lines = []
        report_lines.append("=" * 60)
        report_lines.append("AUTO-HEALING AI - COMPREHENSIVE REPORT")
        report_lines.append("=" * 60)
        report_lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("")
        
        # Current Metrics Summary
        report_lines.append("📊 CURRENT METRICS SUMMARY")
        report_lines.append("-" * 30)
        
        if self.last_snapshot["no_inject"] is not None:
            df_no = self.last_snapshot["no_inject"]
            report_lines.append(f"No-Injection Engine - {len(df_no)} servers")
            report_lines.append(f"Average CPU: {df_no['CPU'].mean():.1f}%")
            report_lines.append(f"Average Memory: {df_no['Memory'].mean():.1f}%")
            report_lines.append(f"Total Errors: {df_no['Errors'].sum():.1f}")
            report_lines.append("")
        
        if self.last_snapshot["inject"] is not None:
            df_inj = self.last_snapshot["inject"]
            report_lines.append(f"Injected Engine - {len(df_inj)} servers")
            report_lines.append(f"Average CPU: {df_inj['CPU'].mean():.1f}%")
            report_lines.append(f"Average Memory: {df_inj['Memory'].mean():.1f}%")
            report_lines.append(f"Total Errors: {df_inj['Errors'].sum():.1f}")
            report_lines.append("")
        
        # Graph Comparison
        report_lines.append("📈 GRAPH COMPARISON ANALYSIS")
        report_lines.append("-" * 30)
        comparison_result = self.compare_graphs()
        report_lines.append(comparison_result)
        report_lines.append("")
        
        # Available Logs
        report_lines.append("📝 AVAILABLE LOGS")
        report_lines.append("-" * 30)
        
        # Check incidents log
        if os.path.exists(INCIDENTS_LOG_PATH):
            try:
                with open(INCIDENTS_LOG_PATH, 'r', encoding='utf-8') as f:
                    incidents = f.readlines()
                report_lines.append(f"Incidents Log: {len(incidents)} entries")
                if incidents:
                    report_lines.append("Recent incidents:")
                    for incident in incidents[-5:]:  # Last 5 incidents
                        report_lines.append(f"  • {incident.strip()}")
            except Exception as e:
                report_lines.append(f"Incidents Log: Error reading - {e}")
        else:
            report_lines.append("Incidents Log: Not found")
        
        # Check risk log
        if os.path.exists(RISK_LOG_PATH):
            try:
                with open(RISK_LOG_PATH, 'r', encoding='utf-8') as f:
                    risks = f.readlines()
                report_lines.append(f"Risk Log: {len(risks)} entries")
                if risks:
                    report_lines.append("Recent risks:")
                    for risk in risks[-5:]:  # Last 5 risks
                        report_lines.append(f"  • {risk.strip()}")
            except Exception as e:
                report_lines.append(f"Risk Log: Error reading - {e}")
        else:
            report_lines.append("Risk Log: Not found")
        
        report_lines.append("")
        
        # Engine Status
        report_lines.append("🔧 ENGINE STATUS")
        report_lines.append("-" * 30)
        no_running = self.thread_no and self.thread_no.is_alive()
        inj_running = self.thread_inj and self.thread_inj.is_alive()
        report_lines.append(f"No-Injection Engine: {'🟢 Running' if no_running else '🔴 Stopped'}")
        report_lines.append(f"Injected Engine: {'🟢 Running' if inj_running else '🔴 Stopped'}")
        report_lines.append("")
        
        # Recommendations
        report_lines.append("💡 RECOMMENDATIONS")
        report_lines.append("-" * 30)
        if no_running and inj_running:
            report_lines.append("• Both engines are running - monitor for differences")
            report_lines.append("• Use comparison tools to analyze performance variations")
        elif no_running or inj_running:
            report_lines.append("• Only one engine is running - start the other for comparison")
        else:
            report_lines.append("• No engines running - start engines to collect data")
        
        report_lines.append("• Use 'Compare Graphs' button for detailed analysis")
        report_lines.append("• Export comparison data for external analysis")
        
        report_lines.append("")
        report_lines.append("=" * 60)
        report_lines.append("End of Report")
        report_lines.append("=" * 60)
        
        return "\n".join(report_lines)

    def _export_comparison_data(self, file_path):
        """Export comparison data to CSV."""
        try:
            with open(file_path, "w", newline="", encoding='utf-8') as f:
                f.write("Server,No_Injection_CPU,No_Injection_Memory,No_Injection_Errors,Injected_CPU,Injected_Memory,Injected_Errors,Difference_CPU,Difference_Memory,Difference_Errors\n")
                
                all_servers = set(self.last_snapshot["no_inject"]["Server"]) | set(self.last_snapshot["inject"]["Server"])
                
                for server in all_servers:
                    no_inj_row = self.last_snapshot["no_inject"][self.last_snapshot["no_inject"]["Server"] == server]
                    inj_row = self.last_snapshot["inject"][self.last_snapshot["inject"]["Server"] == server]
                    
                    if not no_inj_row.empty and not inj_row.empty:
                        no_inj_cpu = float(no_inj_row.iloc[0]["CPU"])
                        no_inj_mem = float(no_inj_row.iloc[0]["Memory"])
                        no_inj_err = float(no_inj_row.iloc[0]["Errors"])
                        
                        inj_cpu = float(inj_row.iloc[0]["CPU"])
                        inj_mem = float(inj_row.iloc[0]["Memory"])
                        inj_err = float(inj_row.iloc[0]["Errors"])
                        
                        diff_cpu = abs(no_inj_cpu - inj_cpu)
                        diff_mem = abs(no_inj_mem - inj_mem)
                        diff_err = abs(no_inj_err - inj_err)
                        
                        f.write(f"{server},{no_inj_cpu:.1f},{no_inj_mem:.1f},{no_inj_err:.1f},{inj_cpu:.1f},{inj_mem:.1f},{inj_err:.1f},{diff_cpu:.1f},{diff_mem:.1f},{diff_err:.1f}\n")
            
            self.append_log(f"[UI] Comparison data exported to {file_path}", "system")
        except Exception as e:
            self.append_log(f"[UI] Error exporting comparison data: {e}", "system")

    def _generate_charts(self, timestamp):
        """Generate bar charts and pie charts for the report."""
        try:
            if self.last_snapshot["no_inject"] is None and self.last_snapshot["inject"] is None:
                return
            
            # Create bar chart comparing CPU usage
            if self.last_snapshot["no_inject"] is not None and self.last_snapshot["inject"] is not None:
                self._create_cpu_comparison_bar_chart(timestamp)
                self._create_memory_comparison_bar_chart(timestamp)
                self._create_error_comparison_bar_chart(timestamp)
                self._create_cpu_pie_chart(timestamp)
                self._create_memory_pie_chart(timestamp)
            
        except Exception as e:
            self.append_log(f"[UI] Error generating charts: {e}", "system")

    def _create_cpu_comparison_bar_chart(self, timestamp):
        """Create a bar chart comparing CPU usage between engines."""
        try:
            import matplotlib.pyplot as plt
            
            df_no = self.last_snapshot["no_inject"]
            df_inj = self.last_snapshot["inject"]
            
            servers = list(df_no["Server"])
            no_inj_cpu = list(df_no["CPU"])
            inj_cpu = list(df_inj["CPU"])
            
            x = range(len(servers))
            width = 0.35
            
            fig, ax = plt.subplots(figsize=(10, 6))
            bars1 = ax.bar([i - width/2 for i in x], no_inj_cpu, width, label='No Injection', color='#4CAF50', alpha=0.8)
            bars2 = ax.bar([i + width/2 for i in x], inj_cpu, width, label='Injected', color='#F44336', alpha=0.8)
            
            ax.set_xlabel('Servers')
            ax.set_ylabel('CPU Usage (%)')
            ax.set_title('CPU Usage Comparison: No Injection vs Injected')
            ax.set_xticks(x)
            ax.set_xticklabels(servers, rotation=45)
            ax.legend()
            ax.grid(True, alpha=0.3)
            
            # Add value labels on bars
            for bar in bars1:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height + 1,
                        f'{height:.1f}%', ha='center', va='bottom', fontsize=8)
            
            for bar in bars2:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height + 1,
                        f'{height:.1f}%', ha='center', va='bottom', fontsize=8)
            
            plt.tight_layout()
            chart_path = self.reports_dir / f"cpu_comparison_bar_{timestamp}.png"
            plt.savefig(chart_path, dpi=300, bbox_inches='tight')
            plt.close()
            
            self.append_log(f"[UI] CPU comparison bar chart saved: {chart_path}", "system")
            
        except Exception as e:
            self.append_log(f"[UI] Error creating CPU bar chart: {e}", "system")

    def _create_memory_comparison_bar_chart(self, timestamp):
        """Create a bar chart comparing memory usage between engines."""
        try:
            import matplotlib.pyplot as plt
            
            df_no = self.last_snapshot["no_inject"]
            df_inj = self.last_snapshot["inject"]
            
            servers = list(df_no["Server"])
            no_inj_mem = list(df_no["Memory"])
            inj_mem = list(df_inj["Memory"])
            
            x = range(len(servers))
            width = 0.35
            
            fig, ax = plt.subplots(figsize=(10, 6))
            bars1 = ax.bar([i - width/2 for i in x], no_inj_mem, width, label='No Injection', color='#81C784', alpha=0.8)
            bars2 = ax.bar([i + width/2 for i in x], inj_mem, width, label='Injected', color='#E57373', alpha=0.8)
            
            ax.set_xlabel('Servers')
            ax.set_ylabel('Memory Usage (%)')
            ax.set_title('Memory Usage Comparison: No Injection vs Injected')
            ax.set_xticks(x)
            ax.set_xticklabels(servers, rotation=45)
            ax.legend()
            ax.grid(True, alpha=0.3)
            
            plt.tight_layout()
            chart_path = self.reports_dir / f"memory_comparison_bar_{timestamp}.png"
            plt.savefig(chart_path, dpi=300, bbox_inches='tight')
            plt.close()
            
            self.append_log(f"[UI] Memory comparison bar chart saved: {chart_path}", "system")
            
        except Exception as e:
            self.append_log(f"[UI] Error creating memory bar chart: {e}", "system")

    def _create_error_comparison_bar_chart(self, timestamp):
        """Create a bar chart comparing error rates between engines."""
        try:
            import matplotlib.pyplot as plt
            
            df_no = self.last_snapshot["no_inject"]
            df_inj = self.last_snapshot["inject"]
            
            servers = list(df_no["Server"])
            no_inj_err = list(df_no["Errors"])
            inj_err = list(df_inj["Errors"])
            
            x = range(len(servers))
            width = 0.35
            
            fig, ax = plt.subplots(figsize=(10, 6))
            bars1 = ax.bar([i - width/2 for i in x], no_inj_err, width, label='No Injection', color='#4CAF50', alpha=0.8)
            bars2 = ax.bar([i + width/2 for i in x], inj_err, width, label='Injected', color='#F44336', alpha=0.8)
            
            ax.set_xlabel('Servers')
            ax.set_ylabel('Error Rate')
            ax.set_title('Error Rate Comparison: No Injection vs Injected')
            ax.set_xticks(x)
            ax.set_xticklabels(servers, rotation=45)
            ax.legend()
            ax.grid(True, alpha=0.3)
            
            plt.tight_layout()
            chart_path = self.reports_dir / f"error_comparison_bar_{timestamp}.png"
            plt.savefig(chart_path, dpi=300, bbox_inches='tight')
            plt.close()
            
            self.append_log(f"[UI] Error comparison bar chart saved: {chart_path}", "system")
            
        except Exception as e:
            self.append_log(f"[UI] Error creating error bar chart: {e}", "system")

    def _create_cpu_pie_chart(self, timestamp):
        """Create a pie chart showing CPU distribution."""
        try:
            import matplotlib.pyplot as plt
            
            df_no = self.last_snapshot["no_inject"]
            
            # Calculate average CPU per server
            server_cpu = df_no.groupby('Server')['CPU'].mean()
            
            fig, ax = plt.subplots(figsize=(8, 8))
            colors = plt.cm.Set3(np.linspace(0, 1, len(server_cpu)))
            
            wedges, texts, autotexts = ax.pie(server_cpu.values, labels=server_cpu.index, autopct='%1.1f%%',
                                              colors=colors, startangle=90)
            ax.set_title('CPU Usage Distribution Across Servers (No Injection)')
            
            plt.tight_layout()
            chart_path = self.reports_dir / f"cpu_distribution_pie_{timestamp}.png"
            plt.savefig(chart_path, dpi=300, bbox_inches='tight')
            plt.close()
            
            self.append_log(f"[UI] CPU distribution pie chart saved: {chart_path}", "system")
            
        except Exception as e:
            self.append_log(f"[UI] Error creating CPU pie chart: {e}", "system")

    def _create_memory_pie_chart(self, timestamp):
        """Create a pie chart showing memory distribution."""
        try:
            import matplotlib.pyplot as plt
            import numpy as np
            
            df_no = self.last_snapshot["no_inject"]
            
            # Calculate average memory per server
            server_mem = df_no.groupby('Server')['Memory'].mean()
            
            fig, ax = plt.subplots(figsize=(8, 8))
            colors = plt.cm.Pastel1(np.linspace(0, 1, len(server_mem)))
            
            wedges, texts, autotexts = ax.pie(server_mem.values, labels=server_mem.index, autopct='%1.1f%%',
                                              colors=colors, startangle=90)
            ax.set_title('Memory Usage Distribution Across Servers (No Injection)')
            
            plt.tight_layout()
            chart_path = self.reports_dir / f"memory_distribution_pie_{timestamp}.png"
            plt.savefig(chart_path, dpi=300, bbox_inches='tight')
            plt.close()
            
            self.append_log(f"[UI] Memory distribution pie chart saved: {chart_path}", "system")
            
        except Exception as e:
            self.append_log(f"[UI] Error creating memory pie chart: {e}", "system")

    # --- Window close ---
    def closeEvent(self, event):
        # ensure threads are stopped cleanly
        try:
            if self.thread_no:
                self.thread_no.stop()
                self.thread_no.join(timeout=1)
        except Exception:
            pass
        try:
            if self.thread_inj:
                self.thread_inj.stop()
                self.thread_inj.join(timeout=1)
        except Exception:
            pass
        event.accept()

    # --- boot guard ---
    def _fatal_boot_error(self, msg: str):
        layout = QVBoxLayout(self)
        lbl = QLabel("Engine import failed")
        lbl.setStyleSheet("font-size:18pt; font-weight:bold; color:#b71c1c;")
        layout.addWidget(lbl)
        exp = QPlainTextEdit()
        exp.setReadOnly(True)
        exp.setPlainText(msg)
        layout.addWidget(exp)
        raise SystemExit(f"Engine import failed: {msg}")

    # --- analysis background starter (small helper) ---
    def _start_analysis_background(self, auto_trigger=False):
        # If auto_trigger True, run analyzer briefly after both engines stop.
        # We reuse generate_reports() to avoid duplicating logic.
        if self._analysis_running:
            return
        if auto_trigger:
            # schedule a short delayed run so UI settles
            QTimer.singleShot(200, self.generate_reports)

# run
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = AutoHealingUI()
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
