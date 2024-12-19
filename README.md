# kafka-benchmark-operator

The kafka benchmark charm uses the [OpenMessaging](https://github.com/openmessaging/benchmark) tool to test both producer and consumer performance in the cluster.

The OpenMessaging allows for a distributed deployment, where the charm leader will run the main "manager" process and gather the metrics, whilst other units will act as followers and act as producer/consumers of the cluster.

## Usage

Bootstrap a controller to juju and create a model:

```
juju add-model kafka-benchmark
```

Deploy the cluster:

```
juju deploy kafka --channel=3/edge
juju deploy zookeeper --channel=3/edge
juju relate kafka zookeeper
```

Deploy the benchmark tool and relate:
```
juju deploy kafka-benchmark --channel=latest/edge
juju relate kafka kafka-benchmark
```

### Benchmarking

To kick start a benchmark, execute the following actions:

```
juju run kafka-benchmark/0 prepare  # to set the environment and the cluster
juju run kafka-benchmark/0 run
```

The units will pick-up the command and start executing the benchmark.

### Stop benchmarking

To stop the benchmark, execute:
```
juju run kafka-benchmark/0 stop
```

Optionally, it is possible to clean the current benchmark data using:
```
juju run kafka-benchmark/0 cleanup
```

That will return all kafka-benchmark units to its original condition as well as the kafka cluster.

### COS integration

Relate the kafka benchmark with a [`grafana-agent` operator](https://charmhub.io/grafana-agent). For more details on how to configure COS and its agents, check [the upstream documentation](https://charmhub.io/grafana-agent/docs/using).

Once the `grafana-agent` is deployed, relate it with:

```
juju relate grafana-agent kafka-benchmark
```

The benchmark data will be collected every 10s and sent to prometheus.
