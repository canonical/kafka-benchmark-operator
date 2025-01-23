# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""The config manager class.

This class summarizes all the configuration needed for the workload execution
and returns a model containing that information.
"""

import logging
import os
import time
from abc import abstractmethod
from typing import Any, Optional

from jinja2 import DictLoader, Environment, FileSystemLoader, exceptions
from pydantic import ValidationError

from benchmark.core.models import (
    DatabaseState,
    DPBenchmarkWrapperOptionsModel,
    PeerState,
)
from benchmark.core.structured_config import BenchmarkCharmConfig
from benchmark.core.workload_base import WorkloadBase
from benchmark.literals import DPBenchmarkLifecycleTransition

# Log messages can be retrieved using juju debug-log
logger = logging.getLogger(__name__)


class ConfigManager:
    """Implements the config changes that happen on the workload."""

    def __init__(
        self,
        workload: WorkloadBase,
        database_state: DatabaseState,
        peer_state: PeerState,
        peers: list[str],
        config: BenchmarkCharmConfig,
        labels: str,
        is_leader: bool,
    ):
        self.workload = workload
        self.config = config
        self.peer_state = peer_state
        self.peers = peers
        self.database_state = database_state
        self.labels = labels
        self.is_leader = is_leader

    @abstractmethod
    def get_workload_params(self) -> dict[str, Any]:
        """Return the workload parameters."""
        ...

    def clean(self) -> bool:
        """Clean the benchmark service."""
        try:
            self.workload.disable()
            self.workload.remove(self.workload.paths.service)
            self.workload.reload()

            if self.is_leader:
                self.peer_state.test_name = None

        except Exception as e:
            logger.info(f"Error deleting topic: {e}")
        return self.is_cleaned()

    def is_cleaned(self) -> bool:
        """Checks if the benchmark service has passed its "prepare" status."""
        return bool(self.peer_state.test_name)

    def get_execution_options(
        self,
    ) -> Optional[DPBenchmarkWrapperOptionsModel]:
        """Returns the execution options.

        Raises:
            DPBenchmarkMissingOptionsError: If the database is not ready.
        """
        if not (db := self.database_state.model()):
            # It means we are not yet ready. Return None
            # This check also serves to ensure we have only one valid relation at the time
            return None
        try:
            return DPBenchmarkWrapperOptionsModel(
                test_name=self.peer_state.test_name or "",
                parallel_processes=self.config.parallel_processes,
                threads=self.config.threads,
                duration=self.config.duration,
                run_count=self.config.run_count,
                db_info=db,
                workload_name=self.config.workload_name,
                report_interval=self.config.report_interval,
                labels=self.labels,
                peers=",".join(self.peers),
            )
        except ValidationError:
            # Missing options
            logger.warning("get_execution_options: Missing options")
            return None

    def is_collecting(self) -> bool:
        """Check if the workload is collecting data."""
        # TODO: we define a way to check collection is finished.
        # For now, this feature is not available.
        return False

    def is_uploading(self) -> bool:
        """Check if the workload is uploading data."""
        # TODO: we define a way to check collection is finished.
        # For now, this feature is not available.
        return False

    def prepare(
        self,
    ) -> bool:
        """Prepare the benchmark service."""
        try:
            self._render_params(self.workload.paths.workload_params)
            self._render_service(
                DPBenchmarkLifecycleTransition.PREPARE,
                self.workload.paths.service,
            )
        except Exception as e:
            logger.error(f"Failed to prepare the benchmark service: {e}")
            return False

        if not self.is_leader:
            return True
        test_name_root = self.config.test_name or "benchmark"
        self.peer_state.test_name = f"{test_name_root}-{str(time.time())}"
        return True

    def is_prepared(
        self,
    ) -> bool:
        """Checks if the benchmark service has passed its "prepare" status."""
        return self._check(DPBenchmarkLifecycleTransition.PREPARE) and self.workload.is_halted()

    def run(
        self,
    ) -> bool:
        """Run the benchmark service."""
        try:
            self._render_params(self.workload.paths.workload_params)
            self._render_service(
                DPBenchmarkLifecycleTransition.RUN,
                self.workload.paths.service,
            )
            self.workload.reload()
            self.workload.restart()
        except Exception as e:
            logger.error(f"Failed to run the benchmark service: {e}")
            return False
        return True

    def is_running(
        self,
    ) -> bool:
        """Checks if the benchmark service has passed its "prepare" status."""
        return self._check(DPBenchmarkLifecycleTransition.RUN) and self.workload.is_active()

    def stop(
        self,
    ) -> bool:
        """Stop the benchmark service."""
        try:
            return self.workload.halt()
        except Exception as e:
            logger.error(f"Failed to stop the benchmark service: {e}")
            return False

    def is_stopped(
        self,
    ) -> bool:
        """Checks if the benchmark service has passed its "prepare" status."""
        return self.workload.is_halted()

    def is_failed(
        self,
    ) -> bool:
        """Checks if the benchmark service has failed."""
        return self.workload.is_failed()

    def _render_params(
        self,
        dst_path: str,
    ) -> str | None:
        """Render the workload parameters."""
        return self._render(
            values=self.get_workload_params(),
            template_file=None,
            template_content=self.workload.workload_params_template,
            dst_filepath=dst_path,
        )

    def _render_service(
        self,
        transition: DPBenchmarkLifecycleTransition,
        dst_path: str | None = None,
    ) -> str | None:
        """Render the workload parameters."""
        if not (options := self.get_execution_options()):
            return None
        values = options.dict() | {
            "charm_root": os.environ.get("CHARM_DIR", ""),
            "command": transition.value,
        }
        return self._render(
            values=values,
            template_file=self.workload.paths.service_template,
            template_content=None,
            dst_filepath=dst_path,
        )

    def _check(
        self,
        transition: DPBenchmarkLifecycleTransition,
    ) -> bool:
        if not (
            os.path.exists(self.workload.paths.service)
            and os.path.exists(self.workload.paths.workload_params)
            and (values := self.get_execution_options())
        ):
            return False
        values = values.dict() | {
            "charm_root": self.workload.paths.charm_dir,
            "command": transition.value,
            "target_hosts": values.db_info.hosts,
        }
        compare_svc = "\n".join(
            self.workload.read(self.workload.paths.service) or ""
        ) == self._render(
            values=values,
            template_file=self.workload.paths.service_template,
            template_content=None,
            dst_filepath=None,
        )
        compare_params = "\n".join(
            self.workload.read(self.workload.paths.workload_params)
        ) == self._render(
            values=self.get_workload_params(),
            template_file=None,
            template_content=self.workload.workload_params_template,
            dst_filepath=None,
        )

        return compare_svc and compare_params

    def _render(
        self,
        values: dict[str, Any],
        template_file: str | None,
        template_content: str | None,
        dst_filepath: str | None = None,
    ) -> str | None:
        """Renders from a file or an string content and return final rendered value."""
        try:
            if template_file:
                template_env = Environment(loader=FileSystemLoader(self.workload.paths.templates))
                template = template_env.get_template(template_file)
            else:
                template_env = Environment(
                    loader=DictLoader({"workload_params": template_content or ""})
                )
                template = template_env.get_template("workload_params")
            content = template.render(values)
        except exceptions.TemplateNotFound as e:
            raise e
        if not dst_filepath:
            return content
        self.workload.write(content, dst_filepath)
