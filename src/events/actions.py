# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Handles the actions events for the Kafka benchmark charm."""

import logging

from ops.model import BlockedStatus
from overrides import override

from benchmark.base_charm import DPBenchmarkCharmBase
from benchmark.core.structured_config import BenchmarkCharmConfig
from benchmark.events.actions import ActionsHandler

# TODO: This line must go away once Kafka starts sharing its certificates via client relation

# Log messages can be retrieved using juju debug-log
logger = logging.getLogger(__name__)


class KafkaBenchmarkActionsHandler(ActionsHandler):
    """Handle the actions for the benchmark charm."""

    def __init__(self, charm: DPBenchmarkCharmBase):
        """Initialize the class."""
        super().__init__(charm)
        self.config: BenchmarkCharmConfig = charm.config

    @override
    def _preflight_checks(self) -> bool:
        """Check if we have the necessary relations.

        In kafka case, we need the client relation to be able to connect to the database.
        """
        if (
            int(self.config.parallel_processes) * len(self.charm.peers.all_unit_states().keys())
            < 2
        ):
            logger.error("The number of parallel processes must be greater than 1.")
            self.unit.status = BlockedStatus(
                "The number of parallel processes must be greater than 1."
            )
            return False
        return super()._preflight_checks()
