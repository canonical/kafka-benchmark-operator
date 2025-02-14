#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""This connects the benchmark service to the database and the grafana agent.

The first action after installing the benchmark charm and relating it to the different
apps, is to prepare the db. The user must run the prepare action to create the database.

The prepare action will run the benchmark prepare command to create the database and, at its
end, it sets a systemd target informing the service is ready.

The next step is to execute the run action. This action renders the systemd service file and
starts the service. If the target is missing, then service errors and returns an error to
the user.
"""

import logging
import subprocess

import charms.operator_libs_linux.v0.apt as apt
import ops
from ops.framework import EventBase
from overrides import override

from benchmark.base_charm import DPBenchmarkCharmBase
from benchmark.core.pebble_workload_base import DPBenchmarkPebbleWorkloadBase
from benchmark.core.systemd_workload_base import DPBenchmarkSystemdWorkloadBase
from benchmark.core.workload_base import WorkloadBase
from benchmark.literals import (
    PEER_RELATION,
    DPBenchmarkLifecycleState,
)
from core.models import KafkaBenchmarkCharmConfig
from events.actions import KafkaBenchmarkActionsHandler
from events.kafka import KafkaDatabaseRelationHandler
from events.peers import KafkaPeersRelationHandler

# TODO: This line must go away once Kafka starts sharing its certificates via client relation
from events.tls import JavaTlsHandler
from literals import (
    CLIENT_RELATION_NAME,
    JAVA_VERSION,
)
from managers.config import KafkaConfigManager
from managers.lifecycle import KafkaLifecycleManager

# Log messages can be retrieved using juju debug-log
logger = logging.getLogger(__name__)


def workload_build(workload_params_template: str) -> WorkloadBase:
    """Build the workload."""
    try:
        # Really simple check to see if we have systemd
        subprocess.check_output(["systemctl", "--help"])
    except subprocess.CalledProcessError:
        return DPBenchmarkPebbleWorkloadBase(workload_params_template)
    return DPBenchmarkSystemdWorkloadBase(workload_params_template)


class KafkaBenchmarkOperator(DPBenchmarkCharmBase):
    """Charm the service."""

    config_type = KafkaBenchmarkCharmConfig

    def __init__(self, *args):
        # Load the workload parameters from the template before the constructor
        with open("templates/kafka_workload_params_template.j2") as f:
            self.workload_params_template = f.read()
        super().__init__(*args, db_relation_name=CLIENT_RELATION_NAME)

        self.labels = ",".join([self.model.name, self.unit.name.replace("/", "-")])

        self.database = KafkaDatabaseRelationHandler(
            self,
            CLIENT_RELATION_NAME,
        )
        self.peers = KafkaPeersRelationHandler(self, PEER_RELATION)
        self.tls_handler = JavaTlsHandler(self)

        self.config_manager = KafkaConfigManager(
            workload=self.workload,
            database_state=self.database.state,
            java_tls=self.tls_handler.tls_manager,
            peer_state=self.peers.state,
            peers=self.peers.peers(),
            config=self.config,
            is_leader=self.unit.is_leader(),
            labels=self.labels,
        )

        self.lifecycle = KafkaLifecycleManager(
            peers=self.peers.all_unit_states(),
            this_unit=self.unit,
            config_manager=self.config_manager,
            is_leader=self.unit.is_leader(),
        )
        self.actions = KafkaBenchmarkActionsHandler(self)

        self.framework.observe(self.database.on.db_config_update, self._on_config_changed)
        self.framework.observe(
            self.on[PEER_RELATION].relation_changed,
            self._on_run_check_event,
        )
        self.run_check_deferred = False

    def _on_run_check_event(self, event: EventBase) -> None:
        """Restarts the leader service at RUN time.

        The main challenge with this benchmark is that the leader must wait for all
        the peers to really work. Therefore, we will monitor every change in the peers'
        state and once all the peers move to RUN, we restart the service.
        """
        if not self.unit.is_leader():
            # Only the leader processes this case
            # Only the leader must be started at the end.
            return

        if not self.lifecycle.current() == DPBenchmarkLifecycleState.RUNNING:
            # We only care about the running state
            return

        # We do not need to check for len(peers) > 1 case
        # there is no peer changed in this case
        if not self.lifecycle.check_all_peers_in_state(DPBenchmarkLifecycleState.RUNNING):
            # Not all peers have started yet. We need to wait for them.
            if not self.run_check_deferred:
                event.defer()
                self.run_check_deferred = True
            return

        # All units have started.
        # Now we can restart the leader and finish this event
        self.workload.restart()

    @override
    def _on_install(self, event: EventBase) -> None:
        """Install the charm."""
        apt.add_package(f"openjdk-{JAVA_VERSION}-jre", update_cache=True)

    @override
    def _on_config_changed(self, event):
        """Handle the config changed event."""
        if not self.actions._preflight_checks():
            event.defer()
            return
        return super()._on_config_changed(event)


if __name__ == "__main__":
    ops.main(KafkaBenchmarkOperator)
