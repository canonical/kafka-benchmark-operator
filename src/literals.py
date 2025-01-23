# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""This module contains the constants and models used by the sysbench charm."""

VALID_LOG_LEVELS = ["info", "debug", "warning", "error", "critical"]


TOPIC_NAME = "benchmark_topic"
CLIENT_RELATION_NAME = "kafka"

JAVA_VERSION = "18"

COS_AGENT_RELATION = "cos-agent"
PEER_RELATION = "benchmark-peer"

# PORT constants, used by the benchmark tool to prepare the workers
INITIAL_PORT = 8080
PORT_JUMP = 2

# TODO: This file must go away once Kafka starts sharing its certificates via client relation
TRUSTED_CA_RELATION = "trusted-ca"
TRUSTSTORE_LABEL = "trusted-ca-truststore"
TS_PASSWORD_KEY = "truststore-password"


WORKER_PARAMS_YAML_FILE = "worker_params.yaml"
TEN_YEARS_IN_MINUTES = 5_256_000


class DPBenchmarkError(Exception):
    """Benchmark error."""


class DPBenchmarkExecError(DPBenchmarkError):
    """Sysbench failed to execute a command."""


class DPBenchmarkMultipleRelationsToDBError(DPBenchmarkError):
    """Multiple relations to the same or multiple DBs exist."""


class DPBenchmarkExecFailedError(DPBenchmarkError):
    """Sysbench execution failed error."""


class DPBenchmarkMissingOptionsError(DPBenchmarkError):
    """Sysbench missing options error."""
