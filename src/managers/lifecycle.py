# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Manages the kafka benchmark lifecycle."""

from ops.model import Unit
from overrides import override

from benchmark.core.models import (
    PeerState,
)
from benchmark.literals import (
    DPBenchmarkLifecycleState,
)
from benchmark.managers.config import ConfigManager
from benchmark.managers.lifecycle import LifecycleManager


class KafkaLifecycleManager(LifecycleManager):
    """The lifecycle manager class.

    There is one extra case we must consider: before moving to running, we need to ensure
    all the peers are in the same state are already running.
    """

    def __init__(
        self,
        peers: dict[Unit, PeerState],
        this_unit: Unit,
        config_manager: ConfigManager,
        is_leader: bool = False,
    ):
        super().__init__(peers, this_unit, config_manager, is_leader)
        self.is_leader = is_leader

    @override
    def _peers_state(self) -> DPBenchmarkLifecycleState | None:
        next_state = super()._peers_state()

        if next_state == DPBenchmarkLifecycleState.STOPPED and not self.is_leader:
            # If not leader, then we can only stop if the leader has issued a stop directive
            if self.peers[self.this_unit].stop_directive:
                return DPBenchmarkLifecycleState.STOPPED
            return None

        # Now, there is a special rule: if we are the leader unit, we can only move to RUNNING
        # if all the peers are already running or if peer count is zero
        if not self.is_leader:
            return next_state

        # Check the special case for running && leader
        if next_state == DPBenchmarkLifecycleState.RUNNING:
            if len(self.peers.keys()) == 0:
                return DPBenchmarkLifecycleState.RUNNING
            # Now, as we are not the only unit and we are the leader, we must ensure everyone
            # is in RUNNING state before moving forward:
            if self.check_all_peers_in_state(DPBenchmarkLifecycleState.RUNNING):
                return DPBenchmarkLifecycleState.RUNNING

            # None of the conditions met, we return an empty state
            return None

        return next_state
