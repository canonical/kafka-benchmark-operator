#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock

from ops.model import Unit

from benchmark.core.models import PeerState
from benchmark.literals import DPBenchmarkLifecycleState, DPBenchmarkLifecycleTransition
from benchmark.managers.config import ConfigManager
from benchmark.managers.lifecycle import LifecycleManager


class TestLifecycleManager(LifecycleManager):
    def __init__(
        self,
        peers: dict[Unit, PeerState],
        this_unit: PeerState,
        config_manager: ConfigManager,
    ):
        super().__init__(peers, this_unit, config_manager, is_leader=True)
        self.config_manager.workload.is_failed = MagicMock(return_value=False)
        self.config_manager.is_failed = MagicMock(return_value=False)
        self.config_manager.peer_state.stop_directive = False
        self.config_manager.peer_state.test_name = "test"


class MockPeerState:
    def __init__(self, lifecycle):
        self.lifecycle = lifecycle


def lifecycle_factory(state: DPBenchmarkLifecycleState) -> TestLifecycleManager:
    config = MagicMock()
    this_unit = MagicMock()
    peers = {this_unit: MockPeerState(state)}
    return TestLifecycleManager(
        peers,
        this_unit,
        config,
    )


def test_next_state_clean():
    lifecycle = lifecycle_factory(DPBenchmarkLifecycleState.STOPPED)
    assert lifecycle.next(DPBenchmarkLifecycleTransition.CLEAN) == DPBenchmarkLifecycleState.UNSET


def test_next_state_stop():
    lifecycle = lifecycle_factory(DPBenchmarkLifecycleState.STOPPED)
    lifecycle.config_manager.is_running = MagicMock(return_value=False)

    lifecycle.config_manager.peer_state.stop_directive = True
    # Check the other condition
    assert lifecycle.next(None) is None


def test_next_state_prepare():
    lifecycle = lifecycle_factory(DPBenchmarkLifecycleState.UNSET)
    assert (
        lifecycle.next(DPBenchmarkLifecycleTransition.PREPARE)
        == DPBenchmarkLifecycleState.PREPARING
    )


def test_next_state_prepare_but_peer_already_prepared():
    lifecycle = lifecycle_factory(DPBenchmarkLifecycleState.AVAILABLE)
    # Return None as there are peers in the AVAILABLE or higher state.
    assert lifecycle.next(DPBenchmarkLifecycleTransition.PREPARE) is None


def test_next_state_prepare_available_as_leader():
    lifecycle = lifecycle_factory(DPBenchmarkLifecycleState.UNSET)
    lifecycle.current = MagicMock(return_value=DPBenchmarkLifecycleState.PREPARING)
    assert lifecycle.next(None) == DPBenchmarkLifecycleState.AVAILABLE


def test_next_state_prepare_available_as_follower():
    lifecycle = lifecycle_factory(DPBenchmarkLifecycleState.AVAILABLE)
    lifecycle.current = MagicMock(return_value=DPBenchmarkLifecycleState.UNSET)
    assert lifecycle.next(None) == DPBenchmarkLifecycleState.AVAILABLE


def test_next_state_run_as_leader():
    lifecycle = lifecycle_factory(DPBenchmarkLifecycleState.AVAILABLE)
    lifecycle.current = MagicMock(return_value=DPBenchmarkLifecycleState.AVAILABLE)
    assert lifecycle.next(DPBenchmarkLifecycleTransition.RUN) == DPBenchmarkLifecycleState.RUNNING


def test_next_state_run_as_follower():
    lifecycle = lifecycle_factory(DPBenchmarkLifecycleState.RUNNING)
    lifecycle.current = MagicMock(return_value=DPBenchmarkLifecycleState.AVAILABLE)
    assert lifecycle.next(None) == DPBenchmarkLifecycleState.RUNNING
