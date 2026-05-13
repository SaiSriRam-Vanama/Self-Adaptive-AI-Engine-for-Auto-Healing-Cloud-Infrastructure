# engine_inject.py
import pandas as pd
import random
import datetime
import os
import json
from typing import List, Dict, Any
from engine import AutoHealingEngine
import config

class AutoHealingEngineInjected(AutoHealingEngine):
    """Injected engine — inherits all behavior but injects failures in generate_metrics."""
    def __init__(self):
        super().__init__()
        # use same directories
        os.makedirs(config.LOG_DIR, exist_ok=True)
        os.makedirs(config.REPORTS_DIR, exist_ok=True)

    def generate_metrics(self) -> pd.DataFrame:
        data = []
        for server in self.servers:
            # base values similar to parent
            cpu = random.randint(10, 80)
            memory = random.randint(10, 80)
            errors = round(random.uniform(0, 4), 2)

            # Inject deterministic and random failures if enabled
            if config.INJECT_FAILURES:
                # deterministic injection by cycle: engine.current_cycle is managed in UI thread
                if getattr(self, "current_cycle", 0) == 2 and server == "server-1":
                    cpu = 95
                if getattr(self, "current_cycle", 0) == 3 and server == "server-3":
                    errors = 10.0
                # random spike chance
                if random.random() < 0.12:
                    cpu = random.randint(85, 98)
                    errors = round(random.uniform(6, 12), 2)

            data.append([server, cpu, memory, errors])
        return pd.DataFrame(data, columns=["Server", "CPU", "Memory", "Errors"])

    # Optionally override healing_action to tag logs differently
    def healing_action(self, server: str, issues: List[str]):
        super().healing_action(server, issues)
        # write injected-specific log file too
        with open(os.path.join(config.LOG_DIR, "incidents_inject.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(self.logs[-1]) + "\n")
