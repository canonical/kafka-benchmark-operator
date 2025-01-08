# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""The core models for the wrapper script."""

from enum import Enum

from prometheus_client import Gauge
from pydantic import BaseModel


class BenchmarkCommand(str, Enum):
    """Enum to hold the benchmark phase."""

    PREPARE = "prepare"
    RUN = "run"
    STOP = "stop"
    COLLECT = "collect"
    UPLOAD = "upload"
    CLEANUP = "cleanup"


class ProcessStatus(str, Enum):
    """Enum to hold the process status."""

    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    TO_START = "to_start"


class ProcessModel(BaseModel):
    """Model to hold the process information."""

    cmd: str
    pid: int = -1
    status: str = ProcessStatus.TO_START
    user: str | None = None
    group: str | None = None
    cwd: str | None = None


class MetricOptionsModel(BaseModel):
    """Model to hold the metrics."""

    label: str | None = None
    extra_labels: list[str] = []
    description: str | None = None


class WorkloadCLIArgsModel(BaseModel):
    """Model to hold the workload options."""

    test_name: str
    command: BenchmarkCommand
    workload: str
    threads: int
    parallel_processes: int
    duration: int
    run_count: int
    report_interval: int
    extra_labels: str
    log_file: str = "/var/log/dpe_benchmark_workload.log"
    peers: str


class BenchmarkMetrics:
    """Class to hold the benchmark metrics."""

    def __init__(
        self,
        options: MetricOptionsModel,
    ):
        self.options = options
        self.metrics = {}

    def add(self, sample: BaseModel):
        """Add the benchmark to the prometheus metric."""
        for key, value in sample.dict().items():
            if f"{self.options.label}_{key}" not in self.metrics:
                self.metrics[f"{self.options.label}_{key}"] = Gauge(
                    f"{self.options.label}_{key}",
                    f"{self.options.description} {key}",
                    ["model", "unit"],
                )
            self.metrics[f"{self.options.label}_{key}"].labels(*self.options.extra_labels).set(
                value
            )



class KafkaBenchmarkSample(BaseModel):
    """Sample from the benchmark tool."""

    produce_rate: float  # in msgs / s
    produce_throughput: float  # in MB/s
    produce_error_rate: float  # in err/s

    produce_latency_avg: float  # in (ms)
    produce_latency_50: float
    produce_latency_99: float
    produce_latency_99_9: float
    produce_latency_max: float

    produce_delay_latency_avg: float  # in (us)
    produce_delay_latency_50: float
    produce_delay_latency_99: float
    produce_delay_latency_99_9: float
    produce_delay_latency_max: float

    consume_rate: float  # in msgs / s
    consume_throughput: float  # in MB/s
    consume_backlog: float  # in KB


class KafkaBenchmarkSampleMatcher(Enum):
    """Hard-coded regexes to process the benchmark sample."""

    produce_rate: str = r"Pub rate\s+(.*?)\s+msg/s"
    produce_throughput: str = r"Pub rate\s+\d+.\d+\s+msg/s\s+/\s+(.*?)\s+MB/s"
    produce_error_rate: str = r"Pub err\s+(.*?)\s+err/s"
    produce_latency_avg: str = r"Pub Latency \(ms\) avg:\s+(.*?)\s+"
    # Match: Pub Latency (ms) avg: 1478.1 - 50%: 1312.6 - 99%: 4981.5 - 99.9%: 5104.7 - Max: 5110.5
    # Generates: [('1478.1', '1312.6', '4981.5', '5104.7', '5110.5')]
    produce_latency_percentiles: str = r"Pub Latency \(ms\) avg:\s+(.*?)\s+- 50%:\s+(.*?)\s+- 99%:\s+(.*?)\s+- 99.9%:\s+(.*?)\s+- Max:\s+(.*?)\s+"

    # Pub Delay Latency (us) avg: 21603452.9 - 50%: 21861759.0 - 99%: 23621631.0 - 99.9%: 24160895.0 - Max: 24163839.0
    # Generates: [('21603452.9', '21861759.0', '23621631.0', '24160895.0', '24163839.0')]
    produce_latency_delay_percentiles: str = r"Pub Delay Latency \(us\) avg:\s+(.*?)\s+- 50%:\s+(.*?)\s+- 99%:\s+(.*?)\s+- 99.9%:\s+(.*?)\s+- Max:\s+(\d+\.\d+)"

    consume_rate: str = r"Cons rate\s+(.*?)\s+msg/s"
    consume_throughput: str = r"Cons rate\s+\d+.\d+\s+msg/s\s+/\s+(.*?)\s+MB/s"
    consume_backlog: str = r"Backlog:\s+(.*?)\s+K"