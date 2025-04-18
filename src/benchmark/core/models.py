# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""This module abstracts the different DBs and provide a single API set.

The DatabaseRelationManager listens to DB events and manages the relation lifecycles.
The charm interacts with the manager and requests data + listen to some key events such
as changes in the configuration.
"""

import logging
from typing import Any, MutableMapping, Optional

from ops.model import Application, Relation, Unit
from pydantic import BaseModel, error_wrappers, root_validator
from typing_extensions import override

from benchmark.literals import (
    LIFECYCLE_KEY,
    STOP_DIRECTIVE_KEY,
    TEST_NAME_KEY,
    DPBenchmarkLifecycleState,
    DPBenchmarkMissingOptionsError,
    Scope,
)

VALID_LOG_LEVELS = ["info", "debug", "warning", "error", "critical"]


logger = logging.getLogger(__name__)


class SosreportCLIArgsModel(BaseModel):
    """Holds the data specific to connect with the target application."""

    plugins: Optional[list[str]] = []
    plugin_options: Optional[list[str]] = []
    batch: bool = True
    clean: bool = True
    tmp_dir: Optional[str] = "/tmp"
    pack: bool = True

    def __str__(self):
        """Return the string representation of the model."""
        result = ""
        if self.plugins:
            result += (
                "--only-plugins "
                + ",".join(x for x in self.plugins)
                + " --enable-plugins "
                + ",".join(x for x in self.plugins)
            )
        if self.plugin_options:
            result += " ".join([f"-k {opt}" for opt in self.plugin_options])
        if self.batch:
            result += " --batch"
        if self.clean:
            result += " --clean"
        if self.tmp_dir:
            result += f" --tmp-dir {self.tmp_dir}"
        if self.pack:
            result += " -z gzip"
        return result


class DPBenchmarkBaseDatabaseModel(BaseModel):
    """Holds the data specific to connect with the target application."""

    hosts: Optional[list[str]]
    unix_socket: Optional[str]
    username: str
    password: str
    db_name: str
    tls: str | None = None
    tls_ca: str | None = None

    @root_validator(pre=False, skip_on_failure=True)
    @classmethod
    def validate_if_missing_params(cls, field_values):
        """Validate if missing params."""
        missing_param = []
        # Check if the required fields are present
        for f in ["username", "password"]:
            if f not in field_values or field_values[f] is None:
                missing_param.append(f)
        if missing_param:
            raise DPBenchmarkMissingOptionsError(f"{missing_param}")

        # Check if we have the correct endpoint
        if not field_values.get("hosts") and not field_values.get("unix_socket"):
            raise DPBenchmarkMissingOptionsError("Missing endpoint as unix_socket OR host:port")
        return field_values


class DPBenchmarkWrapperOptionsModel(BaseModel):
    """Benchmark execution model.

    This class contains all the config info needed to pass to the benchmark tool wrapper,
    that will be managing the workload.
    """

    test_name: str
    parallel_processes: int
    threads: int
    duration: int
    run_count: int
    workload_name: str
    db_info: DPBenchmarkBaseDatabaseModel
    report_interval: int
    labels: str
    peers: str | None = None


class RelationState:
    """Relation state object."""

    def __init__(
        self,
        component: Application | Unit,
        relation: Relation | None,
        scope: Scope = Scope.UNIT,
    ):
        self.relation = relation
        self.component = component
        self.scope = scope

    @property
    def relation_data(self) -> MutableMapping[str, str]:
        """Returns the relation data."""
        if not self.relation:
            return {}
        return self.relation.data[self.component]

    @property
    def remote_data(self) -> MutableMapping[str, str]:
        """Returns the remote relation data."""
        if not self.relation or self.scope != Scope.APP:
            return {}
        return self.relation.data[self.relation.app]

    def __bool__(self) -> bool:
        """Boolean evaluation based on the existence of self.relation."""
        try:
            return bool(self.relation)
        except AttributeError:
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """Returns the value of the key."""
        ...

    def set(self, items: dict[str, str | None]) -> None:
        """Writes to relation_data."""
        if not self.relation:
            return

        delete_fields = [key for key in items if not items[key]]
        update_content = {k: items[k] for k in items if k not in delete_fields}

        # Only way I could get through the pyright here
        self.relation_data.update({k: v for k, v in update_content.items() if v is not None})

        for field in delete_fields:
            del self.relation_data[field]


class PeerState(RelationState):
    """State collection for the database relation."""

    def __init__(
        self,
        component: Application | Unit,
        relation: Relation | None,
        peer_app: Application | None,
        scope: Scope = Scope.UNIT,
    ):
        super().__init__(
            component=component,
            relation=relation,
            scope=scope,
        )
        self.peer_app = peer_app

    @override
    def get(self, key: str | None = None, default: Any = None) -> Any:
        """Returns the value of the key."""
        if not key:
            return self.relation_data

        return self.relation_data.get(
            key,
            default,
        )

    @property
    def lifecycle(self) -> DPBenchmarkLifecycleState | None:
        """Returns the value of the lifecycle key."""
        return DPBenchmarkLifecycleState(
            self.get(LIFECYCLE_KEY) or DPBenchmarkLifecycleState.UNSET
        )

    @lifecycle.setter
    def lifecycle(self, status: DPBenchmarkLifecycleState | str) -> None:
        """Sets the lifecycle key value."""
        if isinstance(status, DPBenchmarkLifecycleState):
            self.set({LIFECYCLE_KEY: status.value})
        else:
            self.set({LIFECYCLE_KEY: status})

    @property
    def test_name(self) -> str | None:
        """Return the test name."""
        if not self.relation or not self.relation.data or not self.peer_app:
            return None
        return self.relation.data[self.peer_app].get(TEST_NAME_KEY)

    @test_name.setter
    def test_name(self, value: str | None) -> None:
        """Sets the test name."""
        if not self.relation or not self.relation.data or not self.peer_app:
            return

        if not value:
            if TEST_NAME_KEY in self.relation.data[self.peer_app]:
                del self.relation.data[self.peer_app][TEST_NAME_KEY]
            return

        self.relation.data[self.peer_app][TEST_NAME_KEY] = value

    @property
    def stop_directive(self) -> bool | None:
        """Return the test name."""
        if not self.relation or not self.relation.data or not self.peer_app:
            return None
        if self.relation.data[self.peer_app].get(STOP_DIRECTIVE_KEY):
            return True
        return False

    @stop_directive.setter
    def stop_directive(self, stop: bool | None) -> None:
        """Sets the test name."""
        if not self.relation or not self.relation.data or not self.peer_app:
            return

        if STOP_DIRECTIVE_KEY in self.relation.data[self.peer_app]:
            # Cleaning up and then we decide to re-apply or not
            del self.relation.data[self.peer_app][STOP_DIRECTIVE_KEY]

        if stop:
            self.relation.data[self.peer_app][STOP_DIRECTIVE_KEY] = str(stop)


class DatabaseState(RelationState):
    """State collection for the database relation."""

    def __init__(
        self,
        component: Application | Unit,
        relation: Relation | None,
        scope: Scope = Scope.APP,
        data: dict[str, Any] = {},
    ):
        self.database_key = "database"
        super().__init__(
            relation=relation,
            component=component,
            scope=scope,
        )
        self.data = data

    @property
    def tls(self) -> str | None:
        """Returns the TLS to connect to the database."""
        tls = self.data.get("tls")
        if not tls or tls == "disabled":
            return None
        return tls

    @property
    def tls_ca(self) -> str | None:
        """Returns the TLS CA to connect to the database."""
        tls_ca = self.data.get("tls_ca")
        if not tls_ca or tls_ca == "disabled":
            return None
        return tls_ca

    def model(self) -> DPBenchmarkBaseDatabaseModel | None:
        """Returns the value of the key."""
        if not self.relation or not (endpoints := self.remote_data.get("endpoints")):
            return None

        unix_socket = None
        if endpoints.startswith("file://"):
            unix_socket = endpoints[7:]
        try:
            return DPBenchmarkBaseDatabaseModel(
                hosts=endpoints.split(),
                unix_socket=unix_socket,
                username=self.data.get("username", ""),
                password=self.data.get("password", ""),
                db_name=self.remote_data.get(self.database_key, ""),
                tls=self.tls,
                tls_ca=self.tls_ca,
            )
        except error_wrappers.ValidationError as e:
            logger.warning(f"Failed to validate the database model: {e}")
            entries = [entry.get("loc")[0] for entry in e.errors()]
            raise DPBenchmarkMissingOptionsError(f"{entries}")
