"""Local movement tracking package for the adaptive FC controller."""

from tracking.features import FaceFeatureExtractor, FeatureConfig
from tracking.frames import MovementFeature, MovementFrame
from tracking.synthetic import synthetic_sequence

__all__ = [
    "FaceFeatureExtractor",
    "FeatureConfig",
    "MovementFeature",
    "MovementFrame",
    "synthetic_sequence",
]
