"""Phase-gate and release-acceptance public API."""

from .phase_gate import check_phase_gate, gate_report_is_current

__all__ = ["check_phase_gate", "gate_report_is_current"]
