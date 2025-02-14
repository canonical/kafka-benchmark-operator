# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Holds the Kafka relation handler."""

import logging
from typing import Any

from charms.data_platform_libs.v0.data_interfaces import KafkaRequires
from ops.charm import CharmBase
from overrides import override

from benchmark.events.db import DatabaseRelationHandler
from core.models import KafkaDatabaseState
from literals import TOPIC_NAME

# Log messages can be retrieved using juju debug-log
logger = logging.getLogger(__name__)


class KafkaDatabaseRelationHandler(DatabaseRelationHandler):
    """Listens to all the DB-related events and react to them.

    This class will provide the charm with the necessary data to connect to the DB as
    well as the current relation status.
    """

    DATABASE_KEY = "topic"

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str,
    ):
        super().__init__(charm, relation_name)
        self.consumer_prefix = f"{charm.model.name}-{charm.app.name}-benchmark-consumer"
        # We can have only one reference to a Requires object.
        # Hence, we will store it here:
        self._internal_client = KafkaRequires(
            self.charm,
            self.relation_name,
            TOPIC_NAME,
            extra_user_roles="admin",
            consumer_group_prefix=self.consumer_prefix,
        )

    @property
    @override
    def state(self) -> KafkaDatabaseState:
        """Returns the state of the database."""
        if not (self.relation and self.client):
            logger.error("Relation data not found")
            # We may have an error if the relation is gone but self.relation.id still exists
            # or if the relation is not found in the fetch_relation_data yet
            return KafkaDatabaseState(
                self.charm.app,
                None,
            )

        return KafkaDatabaseState(
            self.charm.app,
            self.relation,
            data=self.client.fetch_relation_data().get(self.relation.id, {}),
        )

    @property
    @override
    def client(self) -> Any:
        """Returns the data_interfaces client corresponding to the database."""
        return self._internal_client

    def bootstrap_servers(self) -> list[str] | None:
        """Return the bootstrap servers."""
        if not self.state or not (model := self.state.model()):
            return None
        return model.hosts

    def tls(self) -> tuple[str | None, str | None]:
        """Return the TLS certificates."""
        if not self.state.tls_ca:
            return self.state.tls, None
        return self.state.tls, self.state.tls_ca
