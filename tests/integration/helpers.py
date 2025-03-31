#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
import subprocess
from types import SimpleNamespace
from typing import Literal

import pytest
from pytest_operator.plugin import OpsTest
from tenacity import Retrying, stop_after_delay, wait_fixed

logger = logging.getLogger(__name__)


K8S_DB_MODEL_NAME = "database"
MICROK8S_CLOUD_NAME = "cloudk8s"


CONFIG_OPTS = {"workload_name": "test_mode", "parallel_processes": 2}
SERIES = "jammy"
KAFKA = "kafka"
KAFKA_K8S = "kafka-k8s"
APP_NAME = "kafka-benchmark"
KAFKA_CHANNEL = "3/edge"
DEFAULT_NUM_UNITS = 2
K8S_DB_MODEL_NAME = "database"
MICROK8S_CLOUD_NAME = "uk8s"


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


KRAFT_CONFIG = {
    "profile": "testing",
    "roles": "broker,controller",
}


MODEL_CONFIG = {
    "logging-config": "<root>=INFO;unit=DEBUG",
    "update-status-hook-interval": "1m",
}


def check_service(
    svc_name: str,
    unit_id: int = 0,
    model_name: str = "",
    retry_if_fail: bool = True,
    service_type: Literal["systemd", "pebble"] = "systemd",
) -> bool | None:
    def __check():
        if service_type == "pebble":
            cmd = ["/charm/bin/pebble", "services", svc_name]
        else:
            cmd = ["--", "sudo", "systemctl", "is-active", svc_name]

        try:
            response = subprocess.check_output(
                [
                    "juju",
                    "ssh",
                    f"{APP_NAME}/{unit_id}",
                ]
                + cmd,
                text=True,
                env={"JUJU_MODEL": model_name} if model_name else {},
            ).rstrip()

            logger.info(f"check_service - {response=}")

            return "active" in response and "inactive" not in response

        except Exception as e:
            logger.error(vars(e))
            raise e

    if not retry_if_fail:
        return __check()
    for attempt in Retrying(stop=stop_after_delay(150), wait=wait_fixed(15)):
        with attempt:
            return __check()


async def run_action(
    ops_test, action_name: str, unit_name: str, timeout: int = 30, **action_kwargs
):
    """Runs the given action on the given unit."""
    client_unit = ops_test.model.units.get(unit_name)
    action = await client_unit.run_action(action_name, **action_kwargs)
    result = await action.wait()
    logging.info(f"request results: {result.results}")
    return SimpleNamespace(status=result.status or "completed", response=result.results)


async def get_leader_unit_id(ops_test: OpsTest, app: str = APP_NAME) -> int:
    """Helper function that retrieves the leader unit ID."""
    leader_unit = None
    for unit in ops_test.model.applications[app].units:
        if await unit.is_leader_from_status():
            leader_unit = unit
            break

    if not leader_unit:
        raise ValueError("Leader unit not found")

    return int(leader_unit.name.split("/")[1])
