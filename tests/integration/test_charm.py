#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import pytest
from pytest_operator.plugin import OpsTest

from .helpers import (
    APP_NAME,
    CONFIG_OPTS,
    DEFAULT_NUM_UNITS,
    KAFKA,
    KAFKA_CHANNEL,
    KRAFT_CONFIG,
    MODEL_CONFIG,
    SERIES,
    check_service,
    get_leader_unit_id,
    run_action,
)

logger = logging.getLogger(__name__)


USE_TLS = {
    (use_tls): pytest.param(
        use_tls,
        id="use_tls",
        marks=[
            pytest.mark.group("use_tls"),
        ],
    )
    for use_tls in [True, False]
}


@pytest.mark.parametrize("use_tls", USE_TLS)
@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
async def test_deploy(ops_test: OpsTest, kafka_benchmark_charm, use_tls) -> None:
    """Build and deploy OpenSearch with a single unit and remove it."""
    await ops_test.model.set_config(MODEL_CONFIG)

    await ops_test.model.deploy(
        kafka_benchmark_charm,
        num_units=DEFAULT_NUM_UNITS,
        series=SERIES,
        config=CONFIG_OPTS,
    )
    await ops_test.model.deploy(
        KAFKA,
        channel=KAFKA_CHANNEL,
        config=KRAFT_CONFIG,
        num_units=DEFAULT_NUM_UNITS,
        series=SERIES,
    )
    await ops_test.model.integrate(KAFKA, APP_NAME)
    if use_tls:
        await ops_test.model.deploy(
            "self-signed-certificates",
            num_units=1,
            series=SERIES,
        )
        await ops_test.model.integrate(f"{KAFKA}:certificates", "self-signed-certificates")
        await ops_test.model.integrate(APP_NAME, "self-signed-certificates")

    await ops_test.model.wait_for_idle(apps=[KAFKA], status="active", timeout=2000)
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="waiting", timeout=2000)

    assert len(ops_test.model.applications[APP_NAME].units) == DEFAULT_NUM_UNITS


@pytest.mark.parametrize("use_tls", USE_TLS)
@pytest.mark.abort_on_fail
async def test_prepare(ops_test: OpsTest, use_tls) -> None:
    # async def test_prepare(ops_test: OpsTest, kafka_benchmark_charm) -> None:
    """Build and deploy OpenSearch with a single unit and remove it."""
    leader_id = await get_leader_unit_id(ops_test)

    output = await run_action(ops_test, "prepare", f"{APP_NAME}/{leader_id}")
    assert output.status == "completed"

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="waiting",
        raise_on_blocked=True,
        timeout=15 * 60,
    )


@pytest.mark.parametrize("use_tls", USE_TLS)
@pytest.mark.abort_on_fail
async def test_run(ops_test: OpsTest, use_tls) -> None:
    # async def test_prepare(ops_test: OpsTest, kafka_benchmark_charm) -> None:
    """Build and deploy OpenSearch with a single unit and remove it."""
    leader_id = await get_leader_unit_id(ops_test)

    output = await run_action(ops_test, "run", f"{APP_NAME}/{leader_id}")
    assert output.status == "completed"

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        raise_on_blocked=True,
        timeout=15 * 60,
    )
    assert check_service("dpe_benchmark", unit_id=leader_id)


@pytest.mark.parametrize("use_tls", USE_TLS)
@pytest.mark.abort_on_fail
async def test_stop(ops_test: OpsTest, use_tls) -> None:
    # async def test_prepare(ops_test: OpsTest, kafka_benchmark_charm) -> None:
    """Build and deploy OpenSearch with a single unit and remove it."""
    leader_id = await get_leader_unit_id(ops_test)

    output = await run_action(ops_test, "stop", f"{APP_NAME}/{leader_id}")
    assert output.status == "completed"

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="waiting",
        raise_on_blocked=True,
        timeout=15 * 60,
    )


@pytest.mark.parametrize("use_tls", USE_TLS)
@pytest.mark.abort_on_fail
async def test_restart(ops_test: OpsTest, use_tls) -> None:
    # async def test_prepare(ops_test: OpsTest, kafka_benchmark_charm) -> None:
    """Build and deploy OpenSearch with a single unit and remove it."""
    leader_id = await get_leader_unit_id(ops_test)

    output = await run_action(ops_test, "run", f"{APP_NAME}/{leader_id}")
    assert output.status == "completed"

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        raise_on_blocked=True,
        timeout=15 * 60,
    )
    assert check_service("dpe_benchmark", unit_id=leader_id)


@pytest.mark.parametrize("use_tls", USE_TLS)
@pytest.mark.abort_on_fail
async def test_clean(ops_test: OpsTest, use_tls) -> None:
    # async def test_prepare(ops_test: OpsTest, kafka_benchmark_charm) -> None:
    """Build and deploy OpenSearch with a single unit and remove it."""
    leader_id = await get_leader_unit_id(ops_test)

    output = await run_action(ops_test, "stop", f"{APP_NAME}/{leader_id}")
    assert output.status == "completed"

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="waiting",
        raise_on_blocked=True,
        timeout=15 * 60,
    )

    output = await run_action(ops_test, "cleanup", f"{APP_NAME}/{leader_id}")
    assert output.status == "completed"

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="waiting",
        raise_on_blocked=True,
        timeout=15 * 60,
    )
