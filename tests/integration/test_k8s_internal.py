#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import juju
import pytest
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
    SERIES,
    check_service,
    run_action,
)

logger = logging.getLogger(__name__)

INTERNAL_K8S_MODEL_NAME = K8S_DB_MODEL_NAME + "2"


@pytest.mark.abort_on_fail
async def test_build_and_deploy_k8s_internal(microk8s, kafka_benchmark_charm) -> None:
    logger.info(f"Creating k8s model {INTERNAL_K8S_MODEL_NAME}")
    controller = juju.controller.Controller()
    await controller.connect()
    await controller.add_model(INTERNAL_K8S_MODEL_NAME, cloud_name=microk8s.cloud_name)

    global model_db
    model_db = juju.model.Model()
    await model_db.connect(model_name=INTERNAL_K8S_MODEL_NAME)

    await model_db.deploy(
        KAFKA_K8S,
        channel=KAFKA_CHANNEL,
        config=KRAFT_CONFIG | {"expose_external": "nodeport"},
        num_units=DEFAULT_NUM_UNITS,
        series=SERIES,
        trust=True,
    )

    await model_db.model.deploy(
        kafka_benchmark_charm,
        num_units=1,
        series=SERIES,
        config=CONFIG_OPTS,
    )

    await model_db.model.integrate(KAFKA, APP_NAME)

    await model_db.model.wait_for_idle(apps=[APP_NAME], status="waiting", timeout=2000)
    await model_db.wait_for_idle(apps=[KAFKA_K8S], status="active", timeout=2000)


@pytest.mark.abort_on_fail
async def test_prepare() -> None:
    """Test prepare action."""
    for attempt in Retrying(stop=stop_after_attempt(5), wait=wait_fixed(wait=120), reraise=True):
        with attempt:
            output = await run_action(model_db, "prepare", f"{APP_NAME}/0")
            assert output.status == "completed"

    await model_db.model.wait_for_idle(
        apps=[APP_NAME],
        status="waiting",
        raise_on_blocked=True,
        timeout=15 * 60,
    )


@pytest.mark.abort_on_fail
async def test_run() -> None:
    """Test run action."""
    output = await run_action(model_db, "run", f"{APP_NAME}/0")
    assert output.status == "completed"

    await model_db.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        raise_on_blocked=True,
        timeout=15 * 60,
    )
    assert check_service(svc_name="dpe-benchmark")


@pytest.mark.abort_on_fail
async def test_stop() -> None:
    """Test stop action."""
    output = await run_action(model_db, "stop", f"{APP_NAME}/0")
    assert output.status == "completed"

    await model_db.model.wait_for_idle(
        apps=[APP_NAME],
        status="waiting",
        raise_on_blocked=True,
        timeout=15 * 60,
    )
    assert not check_service(svc_name="dpe-benchmark")


@pytest.mark.abort_on_fail
async def test_restart() -> None:
    """Test stop and restart the benchmark."""
    output = await run_action(model_db, "run", f"{APP_NAME}/0")
    assert output.status == "completed"

    await model_db.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        raise_on_blocked=True,
        timeout=15 * 60,
    )
    assert check_service("dpe-benchmark")


@pytest.mark.abort_on_fail
async def test_clean() -> None:
    """Test cleanup action."""
    output = await run_action(model_db, "stop", f"{APP_NAME}/0")
    assert output.status == "completed"

    await model_db.model.wait_for_idle(
        apps=[APP_NAME],
        status="waiting",
        raise_on_blocked=True,
        timeout=15 * 60,
    )

    output = await run_action(model_db, "cleanup", f"{APP_NAME}/0")
    assert output.status == "completed"

    await model_db.model.wait_for_idle(
        apps=[APP_NAME],
        status="waiting",
        raise_on_blocked=True,
        timeout=15 * 60,
    )
