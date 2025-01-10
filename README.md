# Apache Kafka benchmark operator

The Apache Kafka benchmark charm uses the [OpenMessaging](https://github.com/openmessaging/benchmark) tool to test both producer and consumer performance in the cluster.

The OpenMessaging allows for a distributed deployment, where the charm leader will run the main "manager" process and gather the metrics, whilst other units will act as followers and act as producer/consumers of the cluster.

## Usage


Create a new Juju model:

```
juju add-model kafka-benchmark
```

Deploy Apache Kafka with Juju:

```
juju deploy kafka --channel=3/edge
juju deploy zookeeper --channel=3/edge
juju relate kafka zookeeper
```

Deploy the benchmark tool and relate it to the cluster:

```
juju deploy kafka-benchmark --channel=latest/edge
juju relate kafka kafka-benchmark
```

### Benchmarking

To kick start a benchmark, execute the following actions:

```
juju run kafka-benchmark/leader prepare  # to set the environment and the cluster
juju run kafka-benchmark/leader run
```

The units will pick-up the command and start executing the benchmark.

### Stop benchmarking

To stop the benchmark, execute:

```
juju run kafka-benchmark/leader stop
```

Optionally, it is possible to clean the current benchmark data using:

```
juju run kafka-benchmark/leader cleanup
```

That will return both Apache Kafka benchmark charm and Apache Kafka cluster to their original condition.

### COS integration

Relate the Apache Kafka benchmark with a [`grafana-agent` operator](https://charmhub.io/grafana-agent). For more details on how to deploy and configure COS and its agents, check [the upstream documentation](https://charmhub.io/grafana-agent/docs/using).

Once the `grafana-agent` is deployed, relate it with:

```
juju relate grafana-agent kafka-benchmark
```

The benchmark data will be collected every 10s and sent to prometheus.


## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on enhancements to this charm following best practice guidelines, and [CONTRIBUTING.md](https://github.com/canonical/kafka-benchmark-operator/blob/main/CONTRIBUTING.md) for developer guidance. 

Also, if you truly enjoy working on open-source projects like this one, check out the [career options](https://canonical.com/careers/all) we have at [Canonical](https://canonical.com/). 

## License

Apache Kafka benchmark operator is free software, distributed under the Apache Software License, version 2.0. See [LICENSE](https://github.com/canonical/kafka-benchmark-operator/blob/main/LICENSE) for more information.
