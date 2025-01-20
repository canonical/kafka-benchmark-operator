#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import juju
import pytest
from pytest_operator.plugin import OpsTest

from .helpers import (
    APP_NAME,
    CONFIG_OPTS,
    DEFAULT_NUM_UNITS,
    K8S_DB_MODEL_NAME,
    KAFKA,
    KAFKA_CHANNEL,
    KRAFT_CONFIG,
    SERIES,
)


@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
async def test_deploy_k8s(ops_test: OpsTest, microk8s, kafka_benchmark_charm) -> None:
    """Build the charm and deploy + 3 db units to ensure a cluster is formed."""
    # Create a new model for DB on k8s:
    logging.info(f"Creating k8s model {K8S_DB_MODEL_NAME}")
    controller = juju.controller.Controller()
    await controller.connect()
    await controller.add_model(K8S_DB_MODEL_NAME, cloud_name=microk8s.cloud_name)

    global model_db
    model_db = juju.model.Model()
    await model_db.connect(model_name=K8S_DB_MODEL_NAME)

    await ops_test.model.deploy(
        KAFKA,
        channel=KAFKA_CHANNEL,
        config=KRAFT_CONFIG,
        num_units=DEFAULT_NUM_UNITS,
        series=SERIES,
    )
    await ops_test.model.deploy(
        kafka_benchmark_charm,
        application_name=APP_NAME,
        num_units=DEFAULT_NUM_UNITS,
        config=CONFIG_OPTS,
    )
    await model_db.create_offer(
        endpoint="client",
        offer_name="client",
        application_name=KAFKA,
    )
    await ops_test.model.consume(f"admin/{model_db.name}.client")
    await ops_test.model.relate("client", APP_NAME)

    # # Reduce the update_status frequency until the cluster is deployed
    # async with ops_test.fast_forward("60s"):
    #     await ops_test.model.block_until(
    #         lambda: len(ops_test.model.applications[APP_NAME].units) == 1
    #     )
    await model_db.wait_for_idle(status="active")
    await controller.disconnect()
    await model_db.disconnect()
