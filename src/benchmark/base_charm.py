# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""This class implements the default benchmark workflow.

It is a functional charm that connects the benchmark service to the database and the grafana agent.

The charm should inherit from this class and implement only the specifics for its own tool.

The main step is to execute the run action. This action renders the systemd service file and
starts the service. If the target is missing, then service errors and returns an error to
the user.

This charm should also be the main entry point to all the modelling of your benchmark tool.
"""

import logging
import subprocess
from typing import Any

from charms.data_platform_libs.v0.data_models import TypedCharmBase
from charms.grafana_agent.v0.cos_agent import COSAgentProvider
from ops.charm import CharmEvents, CollectStatusEvent
from ops.framework import EventBase, EventSource
from ops.model import BlockedStatus

from benchmark.core.models import DPBenchmarkLifecycleState
from benchmark.core.pebble_workload_base import DPBenchmarkPebbleWorkloadBase
from benchmark.core.structured_config import BenchmarkCharmConfig
from benchmark.core.systemd_workload_base import DPBenchmarkSystemdWorkloadBase
from benchmark.core.workload_base import WorkloadBase
from benchmark.events.actions import ActionsHandler
from benchmark.events.db import DatabaseRelationHandler
from benchmark.events.peer import PeerRelationHandler
from benchmark.literals import (
    COS_AGENT_RELATION,
    METRICS_PORT,
    PEER_RELATION,
    DPBenchmarkMissingOptionsError,
)
from benchmark.managers.config import ConfigManager
from benchmark.managers.lifecycle import LifecycleManager

# Log messages can be retrieved using juju debug-log
logger = logging.getLogger(__name__)


class DPBenchmarkCheckUploadEvent(EventBase):
    """Informs to check upload is finished."""


class DPBenchmarkCheckCollectEvent(EventBase):
    """Informs to check collect is finished."""


class DPBenchmarkEvents(CharmEvents):
    """Events used by the charm to check the upload."""

    check_collect = EventSource(DPBenchmarkCheckCollectEvent)
    check_upload = EventSource(DPBenchmarkCheckUploadEvent)


def workload_build(workload_params_template: str) -> WorkloadBase:
    """Build the workload."""
    try:
        # Really simple check to see if we have systemd
        subprocess.check_output(["systemctl", "--help"])
    except subprocess.CalledProcessError:
        return DPBenchmarkPebbleWorkloadBase(workload_params_template)
    return DPBenchmarkSystemdWorkloadBase(workload_params_template)


class DPBenchmarkCharmBase(TypedCharmBase[BenchmarkCharmConfig]):
    """The base benchmark class."""

    on = DPBenchmarkEvents()  # pyright: ignore [reportAssignmentType]

    RESOURCE_DEB_NAME = "benchmark-deb"
    workload_params_template = ""

    config_type = BenchmarkCharmConfig

    def __init__(self, *args, db_relation_name: str, workload: WorkloadBase | None = None):
        super().__init__(*args)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.update_status, self._on_update_status)
        self.framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)

        self.database = DatabaseRelationHandler(self, db_relation_name)
        self.peers = PeerRelationHandler(self, PEER_RELATION)
        self.framework.observe(self.database.on.db_config_update, self._on_config_changed)

        # Trigger an update status as we want to know if the relation is ready
        self.framework.observe(self.on[db_relation_name].relation_changed, self._on_update_status)
        self.workload = workload or workload_build(self.workload_params_template)

        self._grafana_agent = COSAgentProvider(
            self,
            relation_name=COS_AGENT_RELATION,
            metrics_endpoints=[],
            refresh_events=[
                self.on.config_changed,
            ],
            scrape_configs=self.scrape_config,
        )
        self.labels = f"{self.model.name},{self.unit.name}"

        self.config_manager = ConfigManager(
            workload=self.workload,
            database_state=self.database.state,
            peer_state=self.peers.state,
            peers=self.peers.peers(),
            config=self.config,
            labels=self.labels,
            is_leader=self.unit.is_leader(),
        )
        self.lifecycle = LifecycleManager(
            self.peers.all_unit_states(),
            self.peers.this_unit(),
            self.config_manager,
        )
        self.actions = ActionsHandler(self)

    ###########################################################################
    #
    #  Charm Event Handlers and Internals
    #
    ###########################################################################

    def _on_install(self, event: EventBase) -> None:
        """Install event."""
        self.workload.install()
        self.peers.state.lifecycle = DPBenchmarkLifecycleState.UNSET

    def _on_collect_unit_status(self, _: CollectStatusEvent | None = None) -> None:
        try:
            status = self.database.state.model()
        except DPBenchmarkMissingOptionsError as e:
            self.unit.status = BlockedStatus(str(e))
            return
        if not status:
            self.unit.status = BlockedStatus("No database relation available")
            return
        # Now, let's check if we need to update our lifecycle position
        self.update_state()
        self.unit.status = self.lifecycle.status

    def _on_update_status(self, _: EventBase | None = None) -> None:
        """Set status for the operator and finishes the service.

        First, we check if there are relations with any meaningful data. If not, then
        this is the most important status to report. Then, we check the details of the
        benchmark service and the benchmark status.
        """
        self._on_collect_unit_status()

    def _on_config_changed(self, event: EventBase) -> None:
        """Config changed event."""
        if not self.config_manager.is_prepared():
            # nothing to do: set the status and leave
            self._on_update_status()
            return

        if (
            self.lifecycle.running
            and self.config_manager.is_running()
            and not self.config_manager.stop()
        ):
            # The stop process may be async so we defer
            logger.warning("Config changed: tried stopping the service but returned False")
            event.defer()
            return
        elif self.lifecycle.running:
            self.config_manager.run()
        self._on_update_status()

    def scrape_config(self) -> list[dict[str, Any]]:
        """Generate scrape config for the Patroni metrics endpoint."""
        return [
            {
                "metrics_path": "/metrics",
                "static_configs": [{"targets": [f"{self._unit_ip()}:{METRICS_PORT}"]}],
                "tls_config": {"insecure_skip_verify": True},
                "scheme": "http",
            }
        ]

    ###########################################################################
    #
    #  Helpers
    #
    ###########################################################################

    def _unit_ip(self) -> str:
        """Current unit ip."""
        bind_address = None
        if PEER_RELATION:
            if binding := self.model.get_binding(PEER_RELATION):
                bind_address = binding.network.bind_address

        return str(bind_address) if bind_address else ""

    def update_state(self) -> None:
        """Update the state of the charm."""
        if (next_state := self.lifecycle.next(None)) and self.lifecycle.current() != next_state:
            self.lifecycle.make_transition(next_state)
