from __future__ import annotations


class OptimizerCoreError(Exception):
    """Base exception for framework-independent optimizer failures."""


class UnsupportedOptimizationMode(OptimizerCoreError):
    pass


class EmptyTargetFiles(OptimizerCoreError):
    pass


class TargetFileReadError(OptimizerCoreError):
    pass
