import time
from engine import AutoHealingEngine
import argparse

def main(num_cycles, sleep_sec):
    engine = AutoHealingEngine()

    print(f"Starting monitoring for {num_cycles} cycles with {sleep_sec}s interval...\n")

    try:
        for cycle in range(num_cycles):
            print(f"Cycle {cycle + 1}:")

            df = engine.generate_metrics()

            engine.update_history(df)

            df = engine.detect_anomalies(df)

            engine.predict_risks()

            engine.plot_metrics(df, save_png=True, cycle_index=cycle + 1)

            print("-" * 40)
            time.sleep(sleep_sec)

    except KeyboardInterrupt:
        print("\nMonitoring interrupted by user. Exiting...")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Auto-Healing AI Engine monitoring cycles.")
    parser.add_argument("--cycles", type=int, default=5, help="Number of monitoring cycles to run.")
    parser.add_argument("--sleep", type=float, default=2, help="Seconds to wait between cycles.")
    args = parser.parse_args()

    main(num_cycles=args.cycles, sleep_sec=args.sleep)
