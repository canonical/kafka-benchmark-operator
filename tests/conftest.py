# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import argparse


def pytest_addoption(parser):
    parser.addoption(
        "--sysbench-charm-series", help="Ubuntu series for sysbench charm (e.g. jammy)"
    )
    parser.addoption(
        "--sysbench-charm-bases-index",
        type=int,
        help="Index of charmcraft.yaml base that matches --sysbench-charm-series",
    )


def pytest_configure(config):
    if (config.option.sysbench_charm_series is None) ^ (
        config.option.sysbench_charm_bases_index is None
    ):
        raise argparse.ArgumentError(
            None, "--sysbench-charm-series and --sysbench-charm-bases-index must be given together"
        )
    # Note: Update defaults whenever charmcraft.yaml is changed
    if config.option.sysbench_charm_series is None:
        config.option.sysbench_charm_series = "jammy"
    if config.option.sysbench_charm_bases_index is None:
        config.option.sysbench_charm_bases_index = 0
