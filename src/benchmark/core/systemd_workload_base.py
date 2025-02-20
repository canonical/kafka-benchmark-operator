# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""This module contains the benchmark workload manager for systemd.

Its implementation follows the WorkloadBase interface. The final workload class
must implement most of the WorkloadBase methods.
"""

import os
import subprocess

from charms.operator_libs_linux.v1.systemd import (
    daemon_reload,
    service_disable,
    service_enable,
    service_failed,
    service_restart,
    service_running,
    service_stop,
)
from typing_extensions import override

from benchmark.core.workload_base import (
    WorkloadBase,
    WorkloadTemplatePaths,
)
from benchmark.literals import BENCHMARK_WORKLOAD_PATH, LINUX_GROUP, LINUX_USER


class DPBenchmarkSystemdTemplatePaths(WorkloadTemplatePaths):
    """Represents the benchmark service template paths."""

    def __init__(self):
        super().__init__()

    @property
    @override
    def service(self) -> str:
        """The optional path to the service file managing the script."""
        return f"/etc/systemd/system/{self.svc_name}.service"

    @property
    @override
    def service_template(self) -> str:
        """The service template file."""
        return "dpe_benchmark.service.j2"

    @property
    @override
    def workload_params(self) -> str:
        """The path to the workload parameters folder."""
        if not self.exists("/root/.benchmark/charmed_parameters"):
            os.makedirs("/root/.benchmark/charmed_parameters", exist_ok=True)
        return "/root/.benchmark/charmed_parameters/" + self.svc_name + ".json"

    @property
    @override
    def results(self) -> str:
        """The path to the results folder."""
        return os.path.join(BENCHMARK_WORKLOAD_PATH, "results")

    @override
    def exists(self, path: str) -> bool:
        """Check if the workload template paths exist."""
        return os.path.exists(path)


class DPBenchmarkSystemdWorkloadBase(WorkloadBase):
    """Represents the benchmark service backed by systemd."""

    def __init__(
        self,
        workload_params_template: str,
    ):
        super().__init__(workload_params_template)
        self.paths = DPBenchmarkSystemdTemplatePaths()

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
    def start(self) -> bool:
        """Starts the workload service."""
        return service_restart(self.paths.svc_name)

    @override
    def restart(self) -> bool:
        """Restarts the benchmark service."""
        return service_restart(self.paths.svc_name)

    @override
    def halt(self) -> bool:
        """Stop the benchmark service."""
        return service_stop(self.paths.svc_name)

    @override
    def reload(self) -> bool:
        """Reloads the script."""
        return daemon_reload()

    def enable(self) -> bool:
        """Enables service."""
        return service_enable(self.paths.svc_name)

    def disable(self) -> bool:
        """Disables service."""
        return service_disable(self.paths.svc_name)

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
        """Executes a command on the workload substrate."""
        exec_env = (env or {}) | os.environ.copy()
        try:
            output = subprocess.run(
                command, cwd=working_dir, env=exec_env, shell=True, capture_output=True
            )
        except subprocess.CalledProcessError:
            return None
        return output.stdout.decode() if output.stdout else None

    @override
    def is_active(self) -> bool:
        """Checks that the workload is active."""
        return service_running(self.paths.svc_name)

    @override
    def _is_stopped(self) -> bool:
        """Checks that the workload is stopped."""
        return not service_running(self.paths.svc_name) and not service_failed(self.paths.svc_name)

    @override
    def is_failed(self) -> bool:
        """Checks if the benchmark service has failed."""
        return service_failed(self.paths.svc_name)
