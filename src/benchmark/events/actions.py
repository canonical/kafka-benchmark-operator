# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""This module abstracts the different DBs and provide a single API set.

The DatabaseRelationHandler listens to DB events and manages the relation lifecycles.
The charm interacts with the manager and requests data + listen to some key events such
as changes in the configuration.
"""

import logging
import typing

if typing.TYPE_CHECKING:
    from benchmark.base_charm import DPBenchmarkCharmBase

from ops.charm import ActionEvent
from ops.framework import EventBase, Object

from benchmark.core.models import DPBenchmarkLifecycleState
from benchmark.literals import (
    DPBenchmarkLifecycleTransition,
    DPBenchmarkMissingOptionsError,
)

logger = logging.getLogger(__name__)


class ActionsHandler(Object):
    """Handle the actions for the benchmark charm."""

    def __init__(self, charm: "DPBenchmarkCharmBase"):
        """Initialize the class."""
        super().__init__(charm, None)
        self.charm = charm
        self.database = charm.database
        self.lifecycle = charm.lifecycle
        self.framework = charm.framework
        self.config_manager = charm.config_manager
        self.peers = charm.peers
        self.unit = charm.unit

        self.framework.observe(self.charm.on.prepare_action, self.on_prepare_action)
        self.framework.observe(self.charm.on.run_action, self.on_run_action)
        self.framework.observe(self.charm.on.stop_action, self.on_stop_action)
        self.framework.observe(self.charm.on.cleanup_action, self.on_clean_action)

        self.framework.observe(
            self.charm.on.check_upload,
            self._on_check_upload,
        )
        self.framework.observe(
            self.charm.on.check_collect,
            self._on_check_collect,
        )

    def _on_check_collect(self, event: EventBase) -> None:
        """Check if the upload is finished."""
        if self.config_manager.is_collecting():
            # Nothing to do, upload is still in progress
            event.defer()
            return

        if self.unit.is_leader():
            self.peers.state.lifecycle = DPBenchmarkLifecycleState.UPLOADING
            # Raise we are running an upload and we will check the status later
            self.charm.on.check_upload.emit()
            return
        self.peers.state.lifecycle = DPBenchmarkLifecycleState.FINISHED

    def _on_check_upload(self, event: EventBase) -> None:
        """Check if the upload is finished."""
        if self.config_manager.is_uploading():
            # Nothing to do, upload is still in progress
            event.defer()
            return
        self.peers.state.lifecycle = DPBenchmarkLifecycleState.FINISHED

    def _preflight_checks(self) -> bool:
        """Check if we have the necessary relations."""
        try:
            return bool(self.database.state.model())
        except DPBenchmarkMissingOptionsError:
            return False

    def on_prepare_action(self, event: ActionEvent) -> None:
        """Process the prepare action."""
        if not self._preflight_checks():
            event.fail("Missing DB or S3 relations")
            return

        if not (state := self.lifecycle.next(DPBenchmarkLifecycleTransition.PREPARE)):
            event.fail("Failed to prepare the benchmark: already done")
            return

        if state != DPBenchmarkLifecycleState.PREPARING:
            event.fail(
                "Another peer is already in prepare state. Wait or call clean action to reset."
            )
            return

        # We process the special case of PREPARE, as explained in lifecycle.make_transition()
        if not self.config_manager.prepare():
            event.fail("Failed to prepare the benchmark")
            return

        self.lifecycle.make_transition(state)
        self.unit.status = self.lifecycle.status
        event.set_results({"message": "Benchmark is being prepared"})

    def on_run_action(self, event: ActionEvent) -> None:
        """Process the run action."""
        if not self._preflight_checks():
            event.fail("Missing DB or S3 relations")
            return

        if not self._process_action_transition(DPBenchmarkLifecycleTransition.RUN):
            event.fail("Failed to run the benchmark")
        event.set_results({"message": "Benchmark has started"})

    def on_stop_action(self, event: ActionEvent) -> None:
        """Process the stop action."""
        if not self._preflight_checks():
            event.fail("Missing DB or S3 relations")
            return

        if not self._process_action_transition(DPBenchmarkLifecycleTransition.STOP):
            event.fail("Failed to stop the benchmark")
        event.set_results({"message": "Benchmark has stopped"})

    def on_clean_action(self, event: ActionEvent) -> None:
        """Process the clean action."""
        if not self._preflight_checks():
            event.fail("Missing DB or S3 relations")
            return

        if not self._process_action_transition(DPBenchmarkLifecycleTransition.CLEAN):
            event.fail("Failed to clean the benchmark")
        event.set_results({"message": "Benchmark is cleaning"})

    def _process_action_transition(self, transition: DPBenchmarkLifecycleTransition) -> bool:
        """Process the action."""
        # First, check if we have an update in our lifecycle state
        self.charm.update_state()

        if not (state := self.lifecycle.next(transition)):
            return False

        self.lifecycle.make_transition(state)
        self.unit.status = self.lifecycle.status
        return True
