# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Structured configuration for the Kafka charm."""

import logging

from charms.data_platform_libs.v0.data_models import BaseConfigModel
from pydantic import Field, validator

logger = logging.getLogger(__name__)


class BenchmarkCharmConfig(BaseConfigModel):
    """Manager for the structured configuration."""

    test_name: str = Field(default="", validate_default=False)
    parallel_processes: int = Field(default=1, validate_default=False, ge=1)
    threads: int = Field(default=1, validate_default=False, ge=1)
    duration: int = Field(default=0, validate_default=False, ge=0)
    run_count: int = Field(default=0, validate_default=False, ge=0)
    workload_name: str = Field(default="default", validate_default=True)
    override_access_hostname: str = Field(default="", validate_default=False)
    report_interval: int = Field(default=1, validate_default=False, ge=1)

    @validator("*", pre=True)
    @classmethod
    def blank_string(cls, value):
        """Check for empty strings."""
        if value == "":
            return None
        return value
