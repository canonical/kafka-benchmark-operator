#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import pytest
from pytest_operator.plugin import OpsTest
from tenacity import Retrying, stop_after_attempt, wait_fixed

from .helpers import (
    APP_NAME,
    CONFIG_OPTS,
    DEFAULT_NUM_UNITS,
    KAFKA_CHANNEL,
    KAFKA_K8S,
    KRAFT_CONFIG,
    SERIES,
    check_service,
    run_action,
)

logger = logging.getLogger(__name__)


MARKS = [
    pytest.param(
        id="k8s_internal",
        marks=pytest.mark.group("k8s_internal"),
    )
]


@pytest.mark.parametrize("", MARKS)
@pytest.mark.abort_on_fail
async def test_build_and_deploy_k8s_internal(ops_test: OpsTest, kafka_benchmark_charm) -> None:
    await ops_test.model.deploy(
        KAFKA_K8S,
        channel=KAFKA_CHANNEL,
        config=KRAFT_CONFIG | {"expose_external": "nodeport"},
        num_units=DEFAULT_NUM_UNITS,
        series=SERIES,
        trust=True,
    )

    await ops_test.model.deploy(
        kafka_benchmark_charm,
        num_units=1,
        series=SERIES,
        config=CONFIG_OPTS,
    )

    await ops_test.model.integrate(KAFKA_K8S, APP_NAME)

    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="waiting", timeout=2000)
    await ops_test.model.wait_for_idle(apps=[KAFKA_K8S], status="active", timeout=2000)


@pytest.mark.parametrize("", MARKS)
@pytest.mark.abort_on_fail
async def test_prepare(ops_test: OpsTest) -> None:
    """Test prepare action."""
    for attempt in Retrying(stop=stop_after_attempt(5), wait=wait_fixed(wait=120), reraise=True):
        with attempt:
            output = await run_action(ops_test, "prepare", f"{APP_NAME}/0")
            assert output.status == "completed"

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="waiting",
        raise_on_blocked=True,
        timeout=15 * 60,
    )


@pytest.mark.parametrize("", MARKS)
@pytest.mark.abort_on_fail
async def test_run(ops_test: OpsTest) -> None:
    """Test run action."""
    for attempt in Retrying(stop=stop_after_attempt(5), wait=wait_fixed(wait=120), reraise=True):
        with attempt:
            output = await run_action(ops_test, "run", f"{APP_NAME}/0")
            assert output.status == "completed"

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        raise_on_blocked=True,
        timeout=15 * 60,
    )
    assert check_service(
        svc_name="dpe-benchmark", service_type="pebble", model_name=ops_test.model_full_name
    )


@pytest.mark.parametrize("", MARKS)
@pytest.mark.abort_on_fail
async def test_stop(ops_test: OpsTest) -> None:
    """Test stop action."""
    output = await run_action(ops_test, "stop", f"{APP_NAME}/0")
    assert output.status == "completed"

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="waiting",
        raise_on_blocked=True,
        timeout=15 * 60,
    )
    assert not check_service(
        svc_name="dpe-benchmark", service_type="pebble", model_name=ops_test.model_full_name
    )


@pytest.mark.parametrize("", MARKS)
@pytest.mark.abort_on_fail
async def test_restart(ops_test: OpsTest) -> None:
    """Test stop and restart the benchmark."""
    for attempt in Retrying(stop=stop_after_attempt(5), wait=wait_fixed(wait=120), reraise=True):
        with attempt:
            output = await run_action(ops_test, "run", f"{APP_NAME}/0")
            assert output.status == "completed"

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        raise_on_blocked=True,
        timeout=15 * 60,
    )
    assert check_service(
        "dpe-benchmark", service_type="pebble", model_name=ops_test.model_full_name
    )


@pytest.mark.parametrize("", MARKS)
@pytest.mark.abort_on_fail
async def test_clean(ops_test: OpsTest) -> None:
    """Test cleanup action."""
    output = await run_action(ops_test, "stop", f"{APP_NAME}/0")
    assert output.status == "completed"

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="waiting",
        raise_on_blocked=True,
        timeout=15 * 60,
    )

    output = await run_action(ops_test, "cleanup", f"{APP_NAME}/0")
    assert output.status == "completed"

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="waiting",
        raise_on_blocked=True,
        timeout=15 * 60,
    )
