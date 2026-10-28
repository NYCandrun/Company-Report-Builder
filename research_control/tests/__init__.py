"""Regression tests for the research control plane."""

import os

# Tests never read or push the host's real conversation transcript.
os.environ["RESEARCH_CONTROL_TRANSCRIPT"] = "/nonexistent/research-control-test-transcript.jsonl"
