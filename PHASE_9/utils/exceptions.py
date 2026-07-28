"""
utils/exceptions.py

Custom exception hierarchy for Phase 9. Using specific exception types
(instead of bare `Exception`) lets the API layer return precise HTTP
status codes and lets callers catch only what they care about.
"""


class DriverBehaviorError(Exception):
    """Base class for all Phase 9 errors."""


class DataLoadError(DriverBehaviorError):
    """Raised when the VED dataset (or any input file) cannot be loaded."""


class DataValidationError(DriverBehaviorError):
    """Raised when input data fails schema / sanity validation."""


class InsufficientDataError(DriverBehaviorError):
    """Raised when a trip / driver does not have enough data points to analyze."""


class FeatureEngineeringError(DriverBehaviorError):
    """Raised when feature extraction fails for a trip or driver."""


class DriverNotFoundError(DriverBehaviorError):
    """Raised when a requested VehId / driver does not exist in the dataset."""


class TripNotFoundError(DriverBehaviorError):
    """Raised when a requested Trip does not exist for a driver."""


class ScoringError(DriverBehaviorError):
    """Raised when driver score computation fails."""


class CoachingGenerationError(DriverBehaviorError):
    """Raised when the LLM coaching layer fails and no fallback is available."""


class ConfigurationError(DriverBehaviorError):
    """Raised when required configuration (e.g. API keys) is missing."""
