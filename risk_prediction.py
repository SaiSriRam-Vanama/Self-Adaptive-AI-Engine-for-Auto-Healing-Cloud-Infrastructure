from risk_utils import moving_average, detect_trend, risk_score

class RiskPredictor:
    def __init__(self, window_size=3):
        self.window_size = window_size
        self.cpu_history = []
        self.mem_history = []
        self.error_history = []

    def update_metrics(self, cpu, mem, error_rate):
        self.cpu_history.append(cpu)
        self.mem_history.append(mem)
        self.error_history.append(error_rate)

        # Keep only the last window_size elements to keep history fixed size
        if len(self.cpu_history) > self.window_size:
            self.cpu_history.pop(0)
            self.mem_history.pop(0)
            self.error_history.pop(0)

    def predict_risk(self):
        """Predict risk based on historical metrics."""
        score = risk_score(self.cpu_history, self.mem_history, self.error_history, self.window_size)
        trend = detect_trend(self.cpu_history, self.window_size)
        risk_level = self._risk_level(score)

        # Debugging output
        print(f"Predicting risk with CPU: {self.cpu_history[-1]}, Memory: {self.mem_history[-1]}, Errors: {self.error_history[-1]}")
        print(f"Risk score: {score:.3f}, Level: {risk_level}, CPU Trend: {trend:.3f}")

        return {
            "risk_score": score,
            "risk_level": risk_level,
            "cpu_trend": trend,
        }

    def _risk_level(self, score):
        if score > 70:
            return 'High'
        elif score > 40:
            return 'Medium'
        else:
            return 'Low'
