from __future__ import annotations

from shared_config.messaging import RabbitMQConsumer, RabbitMQPublisher, RabbitMQTopology
from shared_config.settings import QueueTopologySettings


class FakeChannel:
    def __init__(self) -> None:
        self.exchanges: list[tuple[str, str, bool]] = []
        self.queues: list[tuple[str, bool]] = []
        self.bindings: list[tuple[str, str, str]] = []
        self.published: list[tuple[str, str, str, object]] = []
        self.consumed: list[tuple[str, object, bool]] = []
        self.acked: list[int] = []
        self.nacked: list[tuple[int, bool]] = []

    def exchange_declare(self, *, exchange: str, exchange_type: str, durable: bool) -> None:
        self.exchanges.append((exchange, exchange_type, durable))

    def queue_declare(self, *, queue: str, durable: bool) -> None:
        self.queues.append((queue, durable))

    def queue_bind(self, *, queue: str, exchange: str, routing_key: str) -> None:
        self.bindings.append((queue, exchange, routing_key))

    def basic_publish(self, *, exchange: str, routing_key: str, body: str, properties: object) -> None:
        self.published.append((exchange, routing_key, body, properties))

    def basic_consume(self, *, queue: str, on_message_callback: object, auto_ack: bool = False) -> None:
        self.consumed.append((queue, on_message_callback, auto_ack))

    def basic_ack(self, delivery_tag: int) -> None:
        self.acked.append(delivery_tag)

    def basic_nack(self, delivery_tag: int, requeue: bool = False) -> None:
        self.nacked.append((delivery_tag, requeue))


def test_topology_and_publish_round_trip() -> None:
    channel = FakeChannel()
    topology = RabbitMQTopology.from_settings(QueueTopologySettings())
    publisher = RabbitMQPublisher(channel, topology)

    publisher.declare_topology()
    publisher.publish_json(
        exchange="dungeoncore.jobs",
        routing_key="job.narration",
        payload={"session_id": "session_001"},
        correlation_id="corr_001",
        trace_id="trace_001",
    )

    assert len(channel.exchanges) == 2
    assert len(channel.bindings) == 4
    assert channel.published[0][0] == "dungeoncore.jobs"
    assert channel.published[0][1] == "job.narration"


def test_consumer_ack_and_nack() -> None:
    channel = FakeChannel()
    consumer = RabbitMQConsumer(channel)
    callback = object()

    consumer.consume("dungeoncore.jobs.memory", callback)
    consumer.ack(11)
    consumer.nack(12, requeue=True)

    assert channel.consumed[0][0] == "dungeoncore.jobs.memory"
    assert channel.acked == [11]
    assert channel.nacked == [(12, True)]
