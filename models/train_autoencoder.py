"""Compatibility entry point: the anomaly detector is trained with train_rf.py.

For a mini-project demo, IsolationForest provides an inexpensive anomaly score trained
only on genuine transactions, avoiding a heavyweight GPU dependency.
"""
from train_rf import train
if __name__ == "__main__": train()
