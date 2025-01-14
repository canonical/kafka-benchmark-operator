# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Models for the kafka benchmark tool."""

import logging
import os
from pydantic import BaseModel, validator

from benchmark.core.structured_config import BenchmarkCharmConfig
from benchmark.core.workload_base import WorkloadTemplatePaths
from benchmark.literals import BENCHMARK_WORKLOAD_PATH
from literals import JAVA_VERSION

# Log messages can be retrieved using juju debug-log
logger = logging.getLogger(__name__)


class WorkloadType(BaseModel):
    """Workload type parameters."""

    message_size: int
    producer_rate: int


WorkloadTypeParameters = {
    "test_mode": WorkloadType(message_size=1024, producer_rate=1),
    "default": WorkloadType(message_size=1024, producer_rate=100000),
    "max": WorkloadType(message_size=1024, producer_rate=10000000),
}


class JavaWorkloadPaths:
    """Class to manage the Java trust and keystores."""

    def __init__(self, paths: WorkloadTemplatePaths):
        self.paths = paths

    @property
    def java_home(self) -> str:
        """Return the JAVA_HOME path."""
        return f"/usr/lib/jvm/java-{JAVA_VERSION}-openjdk-amd64"

    @property
    def keytool(self) -> str:
        """Return the keytool path."""
        return os.path.join(self.java_home, "bin/keytool")

    @property
    def truststore(self) -> str:
        """Return the truststore path."""
        return os.path.join(BENCHMARK_WORKLOAD_PATH, "truststore.jks")

    @property
    def ca(self) -> str:
        """Return the CA path."""
        return os.path.join(BENCHMARK_WORKLOAD_PATH, "ca.pem")

    @property
    def server_certificate(self) -> str:
        """Return the CA path."""
        return os.path.join(BENCHMARK_WORKLOAD_PATH, "server_certificate.pem")

    @property
    def keystore(self) -> str:
        """Return the keystore path."""
        return os.path.join(BENCHMARK_WORKLOAD_PATH, "keystore.jks")


class KafkaBenchmarkCharmConfig(BenchmarkCharmConfig):
    """Manager for the structured configuration."""

    @validator("workload_name")
    @classmethod
    def profile_values(cls, value: str) -> str:
        """Check profile config option is valid."""
        if value not in WorkloadTypeParameters.keys():
            raise ValueError(f"Value not one of {str(WorkloadTypeParameters.keys())}")

        return value
