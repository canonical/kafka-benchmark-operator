# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Config manager for the benchmark charm."""

import logging
import os
from functools import cached_property
from math import ceil
from typing import Any

from charms.kafka.v0.client import KafkaClient, NewTopic
from overrides import override
from tenacity import Retrying, stop_after_attempt, wait_fixed

from benchmark.core.models import (
    DatabaseState,
    PeerState,
)
from benchmark.core.structured_config import BenchmarkCharmConfig
from benchmark.core.workload_base import WorkloadBase
from benchmark.literals import (
    DPBenchmarkLifecycleTransition,
)
from benchmark.managers.config import ConfigManager
from core.models import WorkloadTypeParameters

# TODO: This line must go away once Kafka starts sharing its certificates via client relation
from events.tls import JavaTlsStoreManager
from literals import (
    TEN_YEARS_IN_MINUTES,
    WORKER_PARAMS_YAML_FILE,
)

# Log messages can be retrieved using juju debug-log
logger = logging.getLogger(__name__)


class KafkaConfigManager(ConfigManager):
    """The config manager class."""

    def __init__(
        self,
        workload: WorkloadBase,
        database_state: DatabaseState,
        peer_state: PeerState,
        java_tls: JavaTlsStoreManager,
        peers: list[str],
        config: BenchmarkCharmConfig,
        is_leader: bool,
        labels: str = "",
    ):
        super().__init__(workload, database_state, peer_state, peers, config, labels, is_leader)
        self.worker_params_template_file = "kafka_worker_params_template.j2"
        self.java_tls = java_tls
        self.is_leader = is_leader
        self.systemd_service_template_file = "kafka_benchmark.service.j2"

    def _service_args(
        self, args: dict[str, Any], transition: DPBenchmarkLifecycleTransition
    ) -> dict[str, Any]:
        return args | {
            "charm_root": self.workload.paths.charm_dir,
            "command": transition.value,
            "is_coordinator": "" if not self.is_leader else "True",
        }

    @override
    def _render_service(
        self,
        transition: DPBenchmarkLifecycleTransition,
        dst_path: str | None = None,
    ) -> str | None:
        """Render the workload parameters."""
        if not (options := self.get_execution_options()):
            return None
        values = self._service_args(options.dict(), transition)
        return self._render(
            values=values,
            template_file=self.systemd_service_template_file,
            template_content=None,
            dst_filepath=dst_path,
        )

    @override
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
        values = self._service_args(values.dict(), transition)
        compare_svc = "\n".join(self.workload.read(self.workload.paths.service)) == self._render(
            values=values,
            template_file=self.systemd_service_template_file,
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

    def get_worker_params(self) -> dict[str, Any]:
        """Return the workload parameters."""
        # Generate the truststore, if applicable
        self.java_tls.set_truststore()
        if not (db := self.database_state.model()):
            return {}
        num_brokers = len(db.hosts) if db.hosts else 0
        return {
            "total_num_replicas": min(num_brokers, 3),
            # We cannot have quotes nor brackets in this string.
            # Therefore, we render the entire line instead
            "list_of_brokers_bootstrap": "bootstrap.servers={}".format(
                ",".join(db.hosts) if db.hosts else ""
            ),
            "username": db.username,
            "password": db.password,
            "threads": self.config.threads if self.config.threads > 0 else 1,
            "truststore_path": self.java_tls.java_paths.truststore,
            "truststore_pwd": self.java_tls.truststore_pwd,
            "ssl_client_auth": "none",
        }

    def _render_worker_params(
        self,
        dst_path: str | None = None,
    ) -> str | None:
        """Render the worker parameters."""
        return self._render(
            values=self.get_worker_params(),
            template_file=self.worker_params_template_file,
            template_content=None,
            dst_filepath=dst_path,
        )

    @override
    def get_workload_params(self) -> dict[str, Any]:
        """Return the worker parameters."""
        workload = WorkloadTypeParameters[self.config.workload_name]
        clients = ceil((int(self.config.parallel_processes) * len(self.peers)) / 2)
        partitions_per_topic = self.config.threads * clients

        return {
            "partitionsPerTopic": partitions_per_topic,
            "clients": clients,
            "duration": int(self.config.duration / 60)
            if self.config.duration > 0
            else TEN_YEARS_IN_MINUTES,
            "charm_root": self.workload.paths.charm_dir,
            "producerRate": workload.producer_rate,
            "messageSize": workload.message_size,
        }

    @override
    def _render_params(
        self,
        dst_path: str,
    ) -> str | None:
        """Render the workload parameters.

        Overloaded as we need more than one file to be rendered.

        This extra file will rendered in the same folder as `dst_path`, but with a different name.
        """
        super()._render_params(dst_path)
        self._render_worker_params(
            os.path.join(
                os.path.dirname(os.path.abspath(dst_path)),
                WORKER_PARAMS_YAML_FILE,
            )
        )

    @override
    def prepare(self) -> bool:
        """Prepare the benchmark service."""
        super().prepare()
        try:
            for attempt in Retrying(
                stop=stop_after_attempt(4), wait=wait_fixed(wait=20), reraise=True
            ):
                with attempt:
                    if (model := self.database_state.model()) and not self.is_prepared():
                        topic = NewTopic(
                            name=model.db_name,
                            num_partitions=self.config.parallel_processes * (len(self.peers) + 1),
                            replication_factor=self.client.replication_factor,
                        )
                        self.client.create_topic(topic)
        except Exception as e:
            logger.debug(f"Error creating topic: {e}")

        # We may fail to create the topic, as the relation has been recently stablished
        return self.is_prepared()

    @override
    def is_prepared(self) -> bool:
        """Checks if the benchmark service has passed its "prepare" status."""
        try:
            if model := self.database_state.model():
                return model.db_name in self.client._admin_client.list_topics()
        except Exception as e:
            logger.info(f"Error describing topic: {e}")
        return False

    @override
    def clean(self) -> bool:
        """Clean the benchmark service."""
        if not self.is_leader:
            return super().clean()
        # Only applicable for the leader unit
        try:
            if model := self.database_state.model():
                self.client.delete_topics([model.db_name])
            self.workload.remove(self.workload.paths.service)
            self.workload.reload()

        except Exception as e:
            logger.info(f"Error deleting topic: {e}")
        return self.is_cleaned()

    @override
    def is_cleaned(self) -> bool:
        """Checks if the benchmark service has passed its "prepare" status."""
        if not self.is_leader:
            # For a non leader unit, it cannot access kafka as the fetch_relation_data does not return credentials
            # Therefore, for these units, we use the standard check
            return super().is_cleaned()

        try:
            if not (model := self.database_state.model()):
                return False
            return model.db_name not in self.client._admin_client.list_topics()
        except Exception as e:
            logger.info(f"Error describing topic: {e}")
            return False

    @cached_property
    def client(self) -> KafkaClient:
        """Return the Kafka client."""
        has_tls_ca = False
        if os.path.exists(self.java_tls.java_paths.ca):
            has_tls_ca = True

        if not (state := self.database_state.model()):
            return KafkaClient(
                servers=[],
                username=None,
                password=None,
                security_protocol="SASL_PLAINTEXT",
                replication_factor=1,
            )

        host_count = len(state.hosts) if state.hosts else 1
        return KafkaClient(
            servers=state.hosts or [],
            username=state.username,
            password=state.password,
            security_protocol="SASL_SSL" if has_tls_ca else "SASL_PLAINTEXT",
            cafile_path=self.java_tls.java_paths.ca,
            certfile_path=None,
            replication_factor=host_count - 1,
        )
