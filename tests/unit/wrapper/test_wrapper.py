#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock

import benchmark.wrapper.core as core
import wrapper

NON_PROCESSED_LOG_1 = "INFO:benchmark.wrapper.process:[workload pid 24090] 22:23:04.581 [pool-2-thread-1] ERROR ConsumerCoordinator - [Consumer clientId=consumer-sub-000-yUQ7Gao-1, groupId=sub-000-yUQ7Gao] Offset commit with offsets {test-topic-0000000-JvRF6MU-1=OffsetAndMetadata{offset=18281476, leaderEpoch=null, metadata=''}} failed"
NON_PROCESSED_LOG_2 = "INFO:benchmark.wrapper.process:[workload pid 24090] Caused by: org.apache.kafka.common.errors.TimeoutException: Failed to send request after 30000 ms."
PROCESSED_LOG = "INFO:benchmark.wrapper.process:[workload pid 24095] 22:23:03.952 [main] INFO WorkloadGenerator - Pub rate 50064.2 msg/s / 48.9 MB/s | Pub err     0.0 err/s | Cons rate 50065.3 msg/s / 48.9 MB/s | Backlog: 926.0 K | Pub Latency (ms) avg:  6.8 - 50%:  6.4 - 99%: 14.3 - 99.9%: 19.1 - Max: 23.5 | Pub Delay Latency (us) avg: 43.2 - 50%: 45.0 - 99%: 72.0 - 99.9%: 323.0 - Max: 8434.0"


def test_log_processing_regex():
    manager = wrapper.KafkaBenchmarkManager(
        model=MagicMock(),
        args=MagicMock(),
        metrics=MagicMock(),
        unstarted_workers=MagicMock(),
    )
    sample = manager.process_line(PROCESSED_LOG)
    assert sample == core.KafkaBenchmarkSample(
        produce_rate=50064.2,
        produce_throughput=48.9,
        produce_error_rate=0.0,
        produce_latency_avg=6.8,
        produce_latency_50=6.4,
        produce_latency_99=14.3,
        produce_latency_99_9=19.1,
        produce_latency_max=23.5,
        produce_delay_latency_avg=43.2,
        produce_delay_latency_50=45.0,
        produce_delay_latency_99=72.0,
        produce_delay_latency_99_9=323.0,
        produce_delay_latency_max=8434.0,
        consume_rate=50065.3,
        consume_throughput=48.9,
        consume_backlog=926.0,
    )


def test_log_processing_non_metrics_regex():
    manager = wrapper.KafkaBenchmarkManager(
        model=MagicMock(),
        args=MagicMock(),
        metrics=MagicMock(),
        unstarted_workers=MagicMock(),
    )
    sample = manager.process_line(NON_PROCESSED_LOG_1)
    assert sample is None

    sample = manager.process_line(NON_PROCESSED_LOG_2)
    assert sample is None
