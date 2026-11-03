"""researcher worker entry point."""
import sys

from messaging.kafka_runtime import run

if __name__ == "__main__":
    run("researcher", once="--once" in sys.argv)