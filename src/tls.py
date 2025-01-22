# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

# TODO: This file must go away once Kafka starts sharing its certificates via client relation

"""This module contains TLS handlers and managers for the trusted-ca relation."""

import json
import logging
import os
import secrets
import string

from charms.tls_certificates_interface.v3.tls_certificates import (
    generate_csr,
    generate_private_key,
)
from ops.charm import RelationEvent
from ops.model import Application, ModelError, Secret, SecretNotFoundError

from benchmark.base_charm import DPBenchmarkCharmBase
from benchmark.core.workload_base import WorkloadBase
from benchmark.events.handler import RelationHandler
from literals import TRUSTED_CA_RELATION, TRUSTSTORE_LABEL, TS_PASSWORD_KEY
from models import JavaWorkloadPaths

# Log messages can be retrieved using juju debug-log
logger = logging.getLogger(__name__)


class JavaTlsHandler(RelationHandler):
    """Class to manage the Java truststores."""

    def __init__(
        self,
        charm: DPBenchmarkCharmBase,
    ):
        super().__init__(charm, TRUSTED_CA_RELATION)
        self.charm = charm
        self.tls_manager = JavaTlsStoreManager(
            workload=self.charm.workload,
            secret=self.charm.model.get_secret(label=TRUSTSTORE_LABEL),
            is_leader=self.charm.unit.is_leader(),
            app=self.charm.app,
        )

        self.framework.observe(
            self.charm.on[TRUSTED_CA_RELATION].relation_joined,
            self._trusted_relation_joined,
        )
        self.framework.observe(
            self.charm.on[TRUSTED_CA_RELATION].relation_changed,
            self._trusted_relation_changed,
        )
        self.framework.observe(
            self.charm.on[TRUSTED_CA_RELATION].relation_broken,
            self._tls_relation_broken,
        )

    def _tls_relation_broken(self, event: RelationEvent) -> None:
        """Handler for `certificates_relation_broken` event."""
        cas = {
            "csr": "",
            "certificate": "",
            "ca": "",
            "ca-cert": "",
        }
        event.relation.data[self.model.unit]["certificate_signing_requests"] = json.dumps(cas)

    def _trusted_relation_joined(self, event: RelationEvent) -> None:
        """Generate a CSR so the tls-certificates operator works as expected.

        We do not need the CSR or the following certificate. Therefore, we will not use the
        signed certificate nor the generated key.
        """
        if self.charm.unit.is_leader():
            # Leader does not defer this event, so we can generate the private key and publish
            # it across the entire
            self.tls_manager.truststore_pwd = self.tls_manager.generate_password()

        alias = f"{event.app.name}-{event.relation.id}"
        subject = os.uname().nodename
        csr = (
            generate_csr(
                add_unique_id_to_subject_name=bool(alias),
                private_key=generate_private_key(),
                subject=subject,
            )
            .decode()
            .strip()
        )

        csr_dict = [{"certificate_signing_request": csr}]
        event.relation.data[self.model.unit]["certificate_signing_requests"] = json.dumps(csr_dict)

    def _load_relation_data(self, raw_relation_data):
        """Loads relation data from the relation data bag.

        Json loads all data.

        Args:
            raw_relation_data: Relation data from the databag

        Returns:
            dict: Relation data in dict format.
        """
        certificate_data = {}
        for key in raw_relation_data:
            try:
                certificate_data[key] = json.loads(raw_relation_data[key])
            except (json.decoder.JSONDecodeError, TypeError):
                certificate_data[key] = raw_relation_data[key]
        return certificate_data

    def _trusted_relation_changed(self, event: RelationEvent) -> None:
        """Overrides the requirer logic of TLSInterface."""
        if not event.relation or not event.relation.app:
            # This is a relation broken event, we may not have this information available.
            return

        relation_data = self._load_relation_data(event.relation.data[event.relation.app])

        if not (provider_certificates := relation_data.get("certificates", [])):
            logger.warning("No certificates on provider side")
            return

        if provider_certificates and "certificate" in provider_certificates[0]:
            self.tls_manager.set_certificate(
                certificate=provider_certificates[0]["certificate"],
                path=self.tls_manager.java_paths.server_certificate,
            )
        if provider_certificates and "ca" in provider_certificates[0]:
            self.tls_manager.set_certificate(
                certificate=provider_certificates[0]["ca"],
                path=self.tls_manager.java_paths.ca,
            )

        # For now, let's keep all TLS logic here, even if it trigger wider charm changes
        # If we want to later abandon the entire TLS, we can then just remove this file.
        self.charm._on_config_changed(event)


class JavaTlsStoreManager:
    """Class to manage the Java trust and keystores."""

    def __init__(
        self,
        workload: WorkloadBase,
        secret: Secret,
        is_leader: bool,
        app: Application,
    ):
        self.workload = workload
        self.java_paths = JavaWorkloadPaths(self.workload.paths)
        self.secret = secret
        self.ca_alias = "ca"
        self.cert_alias = "server_certificate"
        self.is_leader = is_leader
        self.app = app

    def set_truststore(self) -> bool:
        """Sets the truststore and imports the certificates."""
        if not self.truststore_pwd:
            return False
        return (
            self._set_truststore()
            and self.import_cert(self.ca_alias, self.java_paths.ca)
            and self.import_cert(self.cert_alias, self.java_paths.server_certificate)
        )

    @property
    def truststore_pwd(self) -> str | None:
        """Returns the truststore password."""
        try:
            return self.secret.get_content(refresh=True)[TS_PASSWORD_KEY]
        except (SecretNotFoundError, KeyError):
            return None
        except ModelError as e:
            logger.error(f"Error fetching secret: {e}")
            return None

    @truststore_pwd.setter
    def truststore_pwd(self, pwd: str) -> None:
        """Returns the truststore password."""
        if not self.is_leader:
            # Nothing to do, we manage a single password for the entire application
            return

        if not self.truststore_pwd:
            self.app.add_secret({TS_PASSWORD_KEY: pwd}, label=TRUSTSTORE_LABEL)
            return

        self.secret.set_content({TS_PASSWORD_KEY: pwd})

    def set_certificate(self, certificate: str, path: str) -> None:
        """Sets the unit certificate."""
        self.workload.write(content=certificate, path=path)

    def _set_truststore(self) -> bool:
        """Adds CA to JKS truststore."""
        if not self.workload.paths.exists(self.java_paths.ca):
            return False

        command = f"{self.java_paths.keytool} \
            -import -v -alias {self.ca_alias} \
            -file {self.java_paths.ca} \
            -keystore {self.java_paths.truststore} \
            -storepass {self.truststore_pwd} \
            -noprompt"
        import_cert = bool(
            self.workload.exec(
                command=command,
                working_dir=os.path.dirname(os.path.realpath(self.java_paths.truststore)),
            )
        )
        chown = bool(
            self.workload.exec(
                f"chown {self.workload.user}:{self.workload.group} {self.java_paths.truststore}"
            )
        )
        chmod = bool(self.workload.exec(f"chmod 770 {self.java_paths.truststore}"))
        return import_cert and chown and chmod

    def generate_password(self) -> str:
        """Creates randomized string for use as app passwords.

        Returns:
            String of 32 randomized letter+digit characters
        """
        return "".join([secrets.choice(string.ascii_letters + string.digits) for _ in range(32)])

    def import_cert(self, alias: str, filename: str) -> bool:
        """Add a certificate to the truststore."""
        command = f"{self.java_paths.keytool} \
            -import -v \
            -alias {alias} \
            -file {filename} \
            -keystore {self.java_paths.truststore} \
            -storepass {self.truststore_pwd} -noprompt"
        return bool(self.workload.exec(command))
