# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Structured configuration for the Kafka charm."""

from pydantic import BaseModel, validator
from typing_extensions import override

from benchmark.core.structured_config import BenchmarkCharmConfig


class WorkloadType(BaseModel):
    """Workload type parameters."""

    message_size: int
    producer_rate: int


WorkloadTypeParameters = {
    "default": WorkloadType(message_size=1024, producer_rate=100000),
}


class KafkaBenchmarkCharmConfig(BenchmarkCharmConfig):
    """Manager for the structured configuration."""

    @override
    @validator("workload_name")
    @classmethod
    def profile_values(cls, value: str) -> str:
        """Check profile config option is valid."""
        if value not in WorkloadTypeParameters.keys():
            raise ValueError(f"Value not one of {str(WorkloadTypeParameters.keys())}")

        return value
