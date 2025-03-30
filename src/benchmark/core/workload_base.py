# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Supporting objects for Benchmark charm state."""

import os
from abc import ABC, abstractmethod

from benchmark.literals import BENCHMARK_WORKLOAD_PATH


class WorkloadTemplatePaths(ABC):
    """Interface for workload template paths."""

    def __init__(self):
        if not self.exists(BENCHMARK_WORKLOAD_PATH):
            os.makedirs(BENCHMARK_WORKLOAD_PATH, exist_ok=True)

    @property
    def svc_name(self) -> str:
        """The service name."""
        return "dpe_benchmark"

    @property
    def charm_dir(self) -> str:
        """The path to the benchmark script."""
        # If we do not have this set, then we have a bigger problem
        return os.environ["CHARM_DIR"]

    @property
    def bin(self) -> str:
        """The path to the benchmark script."""
        return os.path.join(self.charm_dir, "src/benchmark/wrapper/main.py")

    @property
    def templates(self) -> str:
        """The path to the workload template folder."""
        return os.path.join(self.charm_dir, "templates")

    @property
    @abstractmethod
    def service(self) -> str:
        """The optional path to the service file managing the python wrapper."""
        ...

    @property
    @abstractmethod
    def service_template(self) -> str:
        """The path to the service template file."""
        ...

    @property
    def workload_params(self) -> str:
        """The path to the workload parameters file."""
        return os.path.join(BENCHMARK_WORKLOAD_PATH, self.svc_name + ".json")

    @property
    @abstractmethod
    def results(self) -> str:
        """The path to the results folder."""
        ...

    def exists(self, path: str) -> bool:
        """Check if the workload path exist."""
        return os.path.exists(path)


class WorkloadBase(ABC):
    """Base interface for common workload operations."""

    paths: WorkloadTemplatePaths
    workload_params_template: str

    def __init__(self, workload_params_template: str):
        self.workload_params_template = workload_params_template

    def install(self) -> bool:
        """Installs the workload."""
        os.chmod(self.paths.bin, 0o700)
        return True

    @property
    @abstractmethod
    def user(self) -> str:
        """Linux user for the process."""
        ...

    @property
    @abstractmethod
    def group(self) -> str:
        """Linux group for the process."""
        ...

    @abstractmethod
    def start(self) -> bool:
        """Starts the workload service."""
        ...

    @abstractmethod
    def restart(self) -> bool:
        """Retarts the workload service."""
        ...

    @abstractmethod
    def halt(self) -> bool:
        """Halts the workload service."""
        ...

    @abstractmethod
    def reload(self) -> bool:
        """Reloads the script."""
        ...

    @abstractmethod
    def enable(self) -> bool:
        """Enables service."""
        ...

    @abstractmethod
    def disable(self) -> bool:
        """Disables service."""
        ...

    @abstractmethod
    def read(self, path: str) -> list[str]:
        """Reads a file from the workload.

        Args:
            path: the full filepath to read from

        Returns:
            List of string lines from the specified path
        """
        ...

    @abstractmethod
    def write(self, content: str, path: str, mode: str = "w") -> None:
        """Writes content to a workload file.

        Args:
            content: string of content to write
            path: the full filepath to write to
            mode: the write mode. Usually "w" for write, or "a" for append. Default "w"
        """
        ...

    def remove(self, path: str) -> None:
        """Remove the specified file."""
        try:
            os.remove(path)
        except OSError:
            pass

    @abstractmethod
    def exec(
        self,
        command: list[str] | str,
        env: dict[str, str] | None = None,
        working_dir: str | None = None,
    ) -> str | None:
        """Executes a command on the workload substrate.

        Returns None if the command failed to be executed.
        """
        ...

    @abstractmethod
    def is_active(self) -> bool:
        """Checks that the workload is active."""
        ...

    @abstractmethod
    def _is_stopped(self) -> bool:
        """Checks that the workload is stopped."""
        ...

    @abstractmethod
    def is_failed(self) -> bool:
        """Checks if the benchmark service has failed."""
        ...

    def is_halted(self) -> bool:
        """Checks if the benchmark service has halted."""
        return self._is_stopped() and not self.is_failed()
