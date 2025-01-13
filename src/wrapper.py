#!/usr/bin/python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""This script runs the benchmark tool, collects its output and forwards to prometheus."""

import argparse
import os
import re

from pydantic import BaseModel
from typing_extensions import override

from benchmark.literals import BENCHMARK_WORKLOAD_PATH
from benchmark.wrapper.core import (
    BenchmarkCommand,
    BenchmarkMetrics,
    KafkaBenchmarkSample,
    KafkaBenchmarkSampleMatcher,
    MetricOptionsModel,
    ProcessModel,
    WorkloadCLIArgsModel,
)
from benchmark.wrapper.main import MainWrapper
from benchmark.wrapper.process import BenchmarkManager, BenchmarkProcess, WorkloadToProcessMapping


class KafkaMainWrapper(MainWrapper):
    """This class is in charge of managing the Kafka benchmark tool."""

    def __init__(self, args: WorkloadCLIArgsModel):
        # As seen in the openmessaging code:
        # https://github.com/openmessaging/benchmark/blob/ \
        #     b10b22767f8063321c90bc9ee1b0aadc5902c31a/benchmark-framework/ \
        #     src/main/java/io/openmessaging/benchmark/WorkloadGenerator.java#L352
        # The report interval is hardcoded to 10 seconds
        args.report_interval = 10
        super().__init__(args)
        metrics = BenchmarkMetrics(
            options=MetricOptionsModel(
                label="openmessaging",
                extra_labels=args.extra_labels.split(","),
                description="Kafka benchmark metric ",
            )
        )
        self.mapping = KafkaWorkloadToProcessMapping(args, metrics)


class KafkaBenchmarkProcess(BenchmarkProcess):
    """This class models one of the processes being executed in the benchmark."""

    @override
    def process_line(self, line: str) -> BaseModel | None:
        """Process the line and return the metric."""
        # Kafka has nothing to process, we never match it
        return None


class KafkaBenchmarkManager(BenchmarkManager):
    """This class is in charge of managing all the processes in the benchmark run."""

    @override
    def process_line(self, line: str) -> BaseModel | None:
        """Process the output of the process."""
        # First, check if we have a match:
        try:
            if not (pub_rate := re.findall(KafkaBenchmarkSampleMatcher.produce_rate.value, line)):
                # Nothing found, we can have an early return
                return None

            if not (
                prod_percentiles := re.findall(
                    KafkaBenchmarkSampleMatcher.produce_latency_percentiles.value, line
                )
            ):
                return None

            if not (
                delay_percentiles := re.findall(
                    KafkaBenchmarkSampleMatcher.produce_latency_delay_percentiles.value, line
                )
            ):
                return None

            return KafkaBenchmarkSample(
                produce_rate=float(pub_rate[0]),
                produce_throughput=float(
                    re.findall(KafkaBenchmarkSampleMatcher.produce_throughput.value, line)[0]
                ),
                produce_error_rate=float(
                    re.findall(KafkaBenchmarkSampleMatcher.produce_error_rate.value, line)[0]
                ),
                produce_latency_avg=float(prod_percentiles[0][0]),
                produce_latency_50=float(prod_percentiles[0][1]),
                produce_latency_99=float(prod_percentiles[0][2]),
                produce_latency_99_9=float(prod_percentiles[0][3]),
                produce_latency_max=float(prod_percentiles[0][4]),
                produce_delay_latency_avg=float(delay_percentiles[0][0]),
                produce_delay_latency_50=float(delay_percentiles[0][1]),
                produce_delay_latency_99=float(delay_percentiles[0][2]),
                produce_delay_latency_99_9=float(delay_percentiles[0][3]),
                produce_delay_latency_max=float(delay_percentiles[0][4]),
                consume_rate=float(
                    re.findall(KafkaBenchmarkSampleMatcher.consume_rate.value, line)[0]
                ),
                consume_throughput=float(
                    re.findall(KafkaBenchmarkSampleMatcher.consume_throughput.value, line)[0]
                ),
                consume_backlog=float(
                    re.findall(KafkaBenchmarkSampleMatcher.consume_backlog.value, line)[0]
                ),
            )
        except Exception:
            return None

    @override
    def start(self):
        """Start the benchmark tool."""
        for worker in self.workers:
            worker.start()
        if self.model:
            # In Kafka, we start the manager after the workers
            BenchmarkProcess.start(self)


class KafkaWorkloadToProcessMapping(WorkloadToProcessMapping):
    """This class maps the workload model to the process."""

    @override
    def _map_prepare(self) -> tuple[BenchmarkManager | None, list[BenchmarkProcess] | None]:
        """Returns the mapping for the prepare phase."""
        # Kafka has nothing to do on prepare
        return None, None

    @override
    def _map_run(self) -> tuple[BenchmarkManager | None, list[BenchmarkProcess] | None]:
        """Returns the mapping for the run phase."""
        driver_path = os.path.join(BENCHMARK_WORKLOAD_PATH, "worker_params.yaml")
        workload_path = os.path.join(BENCHMARK_WORKLOAD_PATH, "dpe_benchmark.json")
        processes: list[BenchmarkProcess] = [
            KafkaBenchmarkProcess(
                model=ProcessModel(
                    cmd=f"""sudo bin/benchmark-worker -p {peer.split(":")[1]} -sp {int(peer.split(":")[1]) + 1}""",
                    cwd=os.path.join(
                        os.path.dirname(os.path.abspath(__file__)),
                        "../openmessaging-benchmark/",
                    ),
                ),
                args=self.args,
                metrics=self.metrics,
            )
            for peer in self.args.peers.split(",")
        ]
        workers = ",".join([f"http://{peer}" for peer in self.args.peers.split(",")])

        manager_process = None
        if self.args.is_coordinator:
            manager_process = ProcessModel(
                cmd=f"""sudo bin/benchmark --workers {workers} --drivers {driver_path} {workload_path}""",
                cwd=os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "../openmessaging-benchmark/",
                ),
            )
        manager = KafkaBenchmarkManager(
            model=manager_process,
            args=self.args,
            metrics=self.metrics,
            unstarted_workers=processes,
        )
        return manager, processes

    @override
    def _map_clean(self) -> tuple[BenchmarkManager | None, list[BenchmarkProcess] | None]:
        """Returns the mapping for the clean phase."""
        # Kafka has nothing to do on prepare
        return None, None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="wrapper", description="Runs the benchmark command as an argument."
    )
    parser.add_argument("--test_name", type=str, help="Test name to be used")
    parser.add_argument("--command", type=str, help="Command to be executed", default="run")
    parser.add_argument("--is_coordinator", type=bool, default=False)
    parser.add_argument(
        "--workload", type=str, help="Name of the workload to be executed", default="default"
    )
    parser.add_argument("--report_interval", type=int, default=10)
    parser.add_argument("--parallel_processes", type=int, default=1)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--duration", type=int, default=0)
    parser.add_argument("--run_count", type=int, default=1)
    parser.add_argument(
        "--peers", type=str, default="", help="comma-separated list of peers to be used."
    )
    parser.add_argument(
        "--extra_labels",
        type=str,
        help="comma-separated list of extra labels to be used.",
        default="",
    )

    # Parse the arguments as dictionary, using the same logic as:
    # https://github.com/python/cpython/blob/ \
    #     47c5a0f307cff3ed477528536e8de095c0752efa/Lib/argparse.py#L134
    args = parser.parse_args()
    args.command = BenchmarkCommand(parser.parse_args().command.lower())
    main_wrapper = KafkaMainWrapper(WorkloadCLIArgsModel.parse_obj(args.__dict__))
    main_wrapper.run()
