# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Holds the Kafka benchmark peer relation handler."""

from overrides import override

from benchmark.events.peer import PeerRelationHandler
from literals import (
    INITIAL_PORT,
    PORT_JUMP,
)


class KafkaPeersRelationHandler(PeerRelationHandler):
    """Listens to all the peer-related events and react to them."""

    @override
    def peers(self) -> list[str]:
        """Return the peers."""
        if not self.relation:
            return []
        return [
            f"{self.relation.data[u]['ingress-address']}:{port}"
            for u in list(self.units()) + [self.this_unit()]
            for port in range(
                INITIAL_PORT,
                INITIAL_PORT + PORT_JUMP * self.charm.config.parallel_processes,
                PORT_JUMP,
            )
        ]
