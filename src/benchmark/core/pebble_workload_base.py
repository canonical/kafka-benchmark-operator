# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""This module contains the benchmark workload manager for pebble.

Its implementation follows the WorkloadBase interface. The final workload class
must implement most of the WorkloadBase methods.
"""

import logging
import os
import subprocess

from typing_extensions import override

from benchmark.core.workload_base import WorkloadBase, WorkloadTemplatePaths
from benchmark.literals import LINUX_GROUP, LINUX_USER

logger = logging.getLogger(__name__)


class DPBenchmarkPebbleTemplatePaths(WorkloadTemplatePaths):
    """Represents the benchmark service template paths."""

    @property
    @override
    def svc_name(self) -> str:
        """The service name."""
        return "dpe-benchmark"

    @property
    @override
    def service(self) -> str:
        """The optional path to the service file managing the script."""
        if not self.exists("/root/.config/pebble/layers"):
            os.makedirs("/root/.config/pebble/layers", exist_ok=True)

        return f"/root/.config/pebble/layers/{self.svc_name}.yaml"

    @property
    @override
    def results(self) -> str:
        """The path to the results folder."""
        return "/root/.benchmark/charmed_parameters/results/"

    @property
    @override
    def service_template(self) -> str:
        """The service template file."""
        return os.path.join(self.templates, "dpe_benchmark.service.j2")

    @override
    def exists(self, path: str) -> bool:
        """Check if the workload template paths exist."""
        return os.path.exists(path)

    @property
    @override
    def workload_params(self) -> str:
        """The path to the workload parameters folder."""
        if not self.exists("/root/.benchmark/charmed_parameters"):
            os.makedirs("/root/.benchmark/charmed_parameters", exist_ok=True)

        return "/root/.benchmark/charmed_parameters/" + self.svc_name + ".json"


class DPBenchmarkPebbleWorkloadBase(WorkloadBase):
    """Represents the benchmark service backed by systemd."""

    def __init__(self, workload_params_template: str):
        super().__init__(workload_params_template)
        self.paths = DPBenchmarkPebbleTemplatePaths()

    @property
    @override
    def user(self) -> str:
        """Linux user for the process."""
        return LINUX_USER

    @property
    @override
    def group(self) -> str:
        """Linux group for the process."""
        return LINUX_GROUP

    @override
    def install(self) -> bool:
        """Installs the workload."""
        os.makedirs("/root/.config/pebble/layers", exist_ok=True)

        return True

    @override
    def start(self) -> bool:
        """Starts the workload service."""
        self.exec("/charm/bin/pebble replan")
        return True

    @override
    def restart(self) -> bool:
        """Restarts the benchmark service."""
        self.exec("/charm/bin/pebble replan")
        return True

    @override
    def halt(self) -> bool:
        """Stop the benchmark service."""
        self.exec(f"/charm/bin/pebble stop {self.paths.svc_name}")
        return True

    @override
    def reload(self) -> bool:
        """Reloads the workload service."""
        self.exec(f"/charm/bin/pebble add {self.paths.svc_name} --combine {self.paths.service}")
        return True

    def enable(self) -> bool:
        """Enables service."""
        return True

    def disable(self) -> bool:
        """Disables service."""
        return False

    @override
    def read(self, path: str) -> list[str]:
        """Reads a file from the workload.

        Args:
            path: the full filepath to read from

        Returns:
            List of string lines from the specified path
        """
        with open(path, "r") as f:
            content = f.read()
        return content.splitlines()

    @override
    def write(self, content: str, path: str, mode: str = "w") -> None:
        """Writes content to a workload file.

        Args:
            content: string of content to write
            path: the full filepath to write to
            mode: the write mode. Usually "w" for write, or "a" for append. Default "w"
        """
        with open(path, mode) as f:
            f.write(content)
            os.chmod(path, 0o640)

    @override
    def exec(
        self,
        command: list[str] | str,
        env: dict[str, str] | None = None,
        working_dir: str | None = None,
    ) -> str | None:
        """Executes a command on the workload substrate.

        Returns None if the command failed to be executed.
        """
        exec_env = (env or {}) | os.environ.copy()
        try:
            output = subprocess.run(
                command, cwd=working_dir, env=exec_env, shell=True, capture_output=True
            )
            logger.debug(f"exec - {output=}")
        except subprocess.CalledProcessError as e:
            logger.error(vars(e))
            return None

        return output.stdout.decode() if output.stdout else None

    @override
    def is_active(self) -> bool:
        """Checks that the workload is active."""
        status = self.exec(f"/charm/bin/pebble services {self.paths.svc_name}")
        if not status:
            logger.debug("no status - active")
            return False

        return status.splitlines()[1].split()[2] == "active"

    @override
    def _is_stopped(self) -> bool:
        """Checks that the workload is stopped."""
        status = self.exec(f"/charm/bin/pebble services {self.paths.svc_name}")
        if not status:
            logger.debug("no status - stopped")
            return False

        return status.splitlines()[1].split()[2] == "inactive"

    @override
    def is_failed(self) -> bool:
        """Checks if the benchmark service has failed."""
        status = self.exec(f"/charm/bin/pebble services {self.paths.svc_name}")
        if not status:
            logger.debug("no status - failed")
            return False

        return not any([self.is_active, self._is_stopped])
