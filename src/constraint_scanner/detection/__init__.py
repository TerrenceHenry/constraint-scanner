"""Detectors and detection service."""

from constraint_scanner.detection.combinatorial import CombinatorialDetector, CombinatorialDetectorSettings
from constraint_scanner.detection.constraint_service import ConstraintService, LoadedConstraint
from constraint_scanner.detection.detector_base import DetectionOutcome, DetectionRejection, DetectorBase, RankedFinding
from constraint_scanner.detection.detector_service import DetectorService, DetectorServiceResult
from constraint_scanner.detection.intra_market import IntraMarketDetector
from constraint_scanner.detection.persistence import OpportunityLifecycle, build_persistence_key, merge_persistence_state
from constraint_scanner.detection.ranking import compute_ranking_score

__all__ = [
    "CombinatorialDetector",
    "CombinatorialDetectorSettings",
    "ConstraintService",
    "DetectionOutcome",
    "DetectionRejection",
    "DetectorBase",
    "DetectorService",
    "DetectorServiceResult",
    "IntraMarketDetector",
    "LoadedConstraint",
    "OpportunityLifecycle",
    "RankedFinding",
    "build_persistence_key",
    "compute_ranking_score",
    "merge_persistence_state",
]
