def moving_average(data, window_size):
    if len(data) < window_size:
        return sum(data) / len(data) if data else 0
    return sum(data[-window_size:]) / window_size

def detect_trend(data, window_size):
    if len(data) < window_size:
        return 0  # Not enough data to detect trend

    y = data[-window_size:]
    x = list(range(window_size))
    n = window_size

    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    sum_xx = sum(xi * xi for xi in x)

    denominator = n * sum_xx - sum_x * sum_x
    if denominator == 0:
        return 0

    slope = (n * sum_xy - sum_x * sum_y) / denominator
    return slope

def risk_score(cpu_history, mem_history, error_history, window_size=3):
    # Calculate average recent CPU, memory, and errors
    cpu_avg = moving_average(cpu_history, window_size)
    mem_avg = moving_average(mem_history, window_size)
    error_avg = moving_average(error_history, window_size)

    # Weighted risk score example
    score = 0.5 * cpu_avg + 0.3 * mem_avg + 0.2 * error_avg
    return score
