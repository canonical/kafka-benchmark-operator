#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.


import subprocess

import juju
import pytest
import yaml
from pytest_operator.plugin import OpsTest

from .helpers import (
    K8S_DB_MODEL_NAME,
    MICROK8S_CLOUD_NAME,
)


@pytest.fixture(scope="module", autouse=True)
async def destroy_model_in_k8s(ops_test):
    yield

    if ops_test.keep_model:
        return
    controller = juju.controller.Controller()
    await controller.connect()
    await controller.destroy_model(K8S_DB_MODEL_NAME)
    await controller.disconnect()

    ctlname = list(yaml.safe_load(subprocess.check_output(["juju", "show-controller"])).keys())[0]

    # We have deployed microk8s, and we do not need it anymore
    subprocess.run(["sudo", "snap", "remove", "--purge", "microk8s"], check=True)
    subprocess.run(["sudo", "snap", "remove", "--purge", "kubectl"], check=True)
    subprocess.run(
        ["juju", "remove-cloud", "--client", "--controller", ctlname, MICROK8S_CLOUD_NAME],
        check=True,
    )


@pytest.fixture(scope="module")
async def kafka_benchmark_charm(ops_test: OpsTest):
    """Kafka charm used for integration testing."""
    charm = await ops_test.build_charm(".")
    return charm
