#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import juju
import pytest
from pytest_operator.plugin import OpsTest
from tenacity import Retrying, stop_after_attempt, wait_fixed

from .helpers import (
    APP_NAME,
    CONFIG_OPTS,
    DEFAULT_NUM_UNITS,
    K8S_DB_MODEL_NAME,
    KAFKA,
    KAFKA_CHANNEL,
    KAFKA_K8S,
    KRAFT_CONFIG,
    MICROK8S_CLOUD_NAME,
    MODEL_CONFIG,
    SERIES,
    check_service,
    get_leader_unit_id,
    run_action,
)

logger = logging.getLogger(__name__)


model_db = None


DEPLOY_MARKS = [
    (
        pytest.param(
            use_tls,
            cloud,
            id=str(use_tls) + f"-{cloud}",
            marks=pytest.mark.group(str(use_tls) + f"-{cloud}"),
        )
    )
    for use_tls in [True, False]
    for cloud in ["vm", MICROK8S_CLOUD_NAME]
]

K8S_MARKS = [
    (
        pytest.param(
            use_tls,
            cloud,
            id=str(use_tls) + f"-{cloud}",
            marks=pytest.mark.group(str(use_tls) + f"-{cloud}"),
        )
    )
    for use_tls in [True, False]
    for cloud in [MICROK8S_CLOUD_NAME]
]

VM_MARKS = [
    (
        pytest.param(
            use_tls,
            cloud,
            id=str(use_tls) + f"-{cloud}",
            marks=pytest.mark.group(str(use_tls) + f"-{cloud}"),
        )
    )
    for use_tls in [True, False]
    for cloud in ["vm"]
]


@pytest.mark.parametrize("use_tls,cloud", K8S_MARKS)
@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
async def test_build_and_deploy_k8s_only(
    ops_test: OpsTest, microk8s, kafka_benchmark_charm, use_tls, cloud
) -> None:
    """Build and deploy with and without TLS on k8s."""
    logging.info(f"Creating k8s model {K8S_DB_MODEL_NAME}")
    controller = juju.controller.Controller()
    await controller.connect()
    await controller.add_model(K8S_DB_MODEL_NAME, cloud_name=microk8s.cloud_name)

    global model_db
    model_db = juju.model.Model()
    await model_db.connect(model_name=K8S_DB_MODEL_NAME)

    await ops_test.model.set_config(MODEL_CONFIG)
    await ops_test.model.deploy(
        kafka_benchmark_charm,
        num_units=DEFAULT_NUM_UNITS,
        series=SERIES,
        config=CONFIG_OPTS,
    )
    await model_db.deploy(
        KAFKA_K8S,
        channel=KAFKA_CHANNEL,
        config=KRAFT_CONFIG | {"expose_external": "nodeport"},
        num_units=DEFAULT_NUM_UNITS,
        series=SERIES,
        trust=True,
    )
    await model_db.create_offer(
        endpoint="kafka-client",
        offer_name="kafka-client",
        application_name=KAFKA_K8S,
    )
    await ops_test.model.consume(f"admin/{model_db.name}.kafka-client")
    await ops_test.model.integrate("kafka-client", f"{APP_NAME}:kafka")

    if use_tls:
        await ops_test.model.deploy(
            "self-signed-certificates",
            num_units=1,
            series=SERIES,
        )
        await ops_test.model.integrate(APP_NAME, "self-signed-certificates")

        await ops_test.model.create_offer(
            endpoint="certificates",
            offer_name="certificates",
            application_name="self-signed-certificates",
        )
        await model_db.consume(f"admin/{ops_test.model.name}.certificates")
        await ops_test.model.integrate("certificates", f"{KAFKA_K8S}:certificates")

    await model_db.wait_for_idle(apps=[KAFKA_K8S], status="active", timeout=2000)
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="waiting", timeout=2000)

    assert len(ops_test.model.applications[APP_NAME].units) == DEFAULT_NUM_UNITS
    await controller.disconnect()
    await model_db.disconnect()


@pytest.mark.parametrize("use_tls,cloud", VM_MARKS)
@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
async def test_build_and_deploy_vm_only(
    ops_test: OpsTest, kafka_benchmark_charm, use_tls, cloud
) -> None:
    """Build and deploy with and without TLS."""
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

    # set the model to the global model_db
    global model_db
    model_db = ops_test.model


@pytest.mark.parametrize("use_tls,cloud", DEPLOY_MARKS)
@pytest.mark.abort_on_fail
async def test_prepare(ops_test: OpsTest, use_tls, cloud) -> None:
    """Test prepare action."""
    leader_id = await get_leader_unit_id(ops_test)

    for attempt in Retrying(stop=stop_after_attempt(5), wait=wait_fixed(wait=120), reraise=True):
        with attempt:
            output = await run_action(ops_test, "prepare", f"{APP_NAME}/{leader_id}")
            assert output.status == "completed"

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="waiting",
        raise_on_blocked=True,
        timeout=15 * 60,
    )


@pytest.mark.parametrize("use_tls,cloud", DEPLOY_MARKS)
@pytest.mark.abort_on_fail
async def test_run(ops_test: OpsTest, use_tls, cloud) -> None:
    """Test run action."""
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


@pytest.mark.parametrize("use_tls,cloud", DEPLOY_MARKS)
@pytest.mark.abort_on_fail
async def test_stop(ops_test: OpsTest, use_tls, cloud) -> None:
    """Test stop action."""
    leader_id = await get_leader_unit_id(ops_test)

    output = await run_action(ops_test, "stop", f"{APP_NAME}/{leader_id}")
    assert output.status == "completed"

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="waiting",
        raise_on_blocked=True,
        timeout=15 * 60,
    )
    assert not check_service("dpe_benchmark", unit_id=leader_id)


@pytest.mark.parametrize("use_tls,cloud", DEPLOY_MARKS)
@pytest.mark.abort_on_fail
async def test_restart(ops_test: OpsTest, use_tls, cloud) -> None:
    """Test stop and restart the benchmark."""
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


@pytest.mark.parametrize("use_tls,cloud", DEPLOY_MARKS)
@pytest.mark.abort_on_fail
async def test_clean(ops_test: OpsTest, use_tls, cloud) -> None:
    """Test cleanup action."""
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
