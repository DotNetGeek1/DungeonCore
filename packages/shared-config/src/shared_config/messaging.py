from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

import pika

from .settings import QueueTopologySettings


@dataclass(frozen=True)
class ExchangeDefinition:
    name: str
    exchange_type: str
    durable: bool = True


@dataclass(frozen=True)
class QueueBinding:
    queue_name: str
    exchange_name: str
    routing_key: str
    durable: bool = True


@dataclass(frozen=True)
class RabbitMQTopology:
    exchanges: tuple[ExchangeDefinition, ...]
    bindings: tuple[QueueBinding, ...]

    @classmethod
    def from_settings(cls, settings: QueueTopologySettings) -> "RabbitMQTopology":
        return cls(
            exchanges=(
                ExchangeDefinition(name=settings.domain_exchange, exchange_type="topic"),
                ExchangeDefinition(name=settings.jobs_exchange, exchange_type="topic"),
            ),
            bindings=(
                QueueBinding(
                    queue_name=settings.orchestration_events_queue,
                    exchange_name=settings.domain_exchange,
                    routing_key=settings.orchestration_events_routing_key,
                ),
                QueueBinding(
                    queue_name=settings.narration_jobs_queue,
                    exchange_name=settings.jobs_exchange,
                    routing_key=settings.narration_jobs_routing_key,
                ),
                QueueBinding(
                    queue_name=settings.memory_jobs_queue,
                    exchange_name=settings.jobs_exchange,
                    routing_key=settings.memory_jobs_routing_key,
                ),
                QueueBinding(
                    queue_name=settings.ui_broadcast_queue,
                    exchange_name=settings.jobs_exchange,
                    routing_key=settings.ui_broadcast_routing_key,
                ),
            ),
        )


class SupportsRabbitChannel(Protocol):
    def exchange_declare(self, *, exchange: str, exchange_type: str, durable: bool) -> None: ...
    def queue_declare(self, *, queue: str, durable: bool) -> None: ...
    def queue_bind(self, *, queue: str, exchange: str, routing_key: str) -> None: ...
    def basic_publish(
        self,
        *,
        exchange: str,
        routing_key: str,
        body: str,
        properties: pika.BasicProperties,
    ) -> None: ...
    def basic_consume(self, *, queue: str, on_message_callback: Any, auto_ack: bool = False) -> None: ...
    def basic_ack(self, delivery_tag: int) -> None: ...
    def basic_nack(self, delivery_tag: int, requeue: bool = False) -> None: ...


class RabbitMQPublisher:
    def __init__(self, channel: SupportsRabbitChannel, topology: RabbitMQTopology) -> None:
        self._channel = channel
        self._topology = topology

    def declare_topology(self) -> None:
        for exchange in self._topology.exchanges:
            self._channel.exchange_declare(
                exchange=exchange.name,
                exchange_type=exchange.exchange_type,
                durable=exchange.durable,
            )
        for binding in self._topology.bindings:
            self._channel.queue_declare(queue=binding.queue_name, durable=binding.durable)
            self._channel.queue_bind(
                queue=binding.queue_name,
                exchange=binding.exchange_name,
                routing_key=binding.routing_key,
            )

    def publish_json(
        self,
        *,
        exchange: str,
        routing_key: str,
        payload: dict[str, Any],
        correlation_id: str,
        trace_id: str,
    ) -> None:
        properties = pika.BasicProperties(
            content_type="application/json",
            correlation_id=correlation_id,
            headers={"trace_id": trace_id},
            delivery_mode=2,
        )
        self._channel.basic_publish(
            exchange=exchange,
            routing_key=routing_key,
            body=json.dumps(payload),
            properties=properties,
        )


class RabbitMQConsumer:
    def __init__(self, channel: SupportsRabbitChannel) -> None:
        self._channel = channel

    def consume(self, queue_name: str, callback: Any) -> None:
        self._channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=False)

    def ack(self, delivery_tag: int) -> None:
        self._channel.basic_ack(delivery_tag)

    def nack(self, delivery_tag: int, *, requeue: bool = False) -> None:
        self._channel.basic_nack(delivery_tag, requeue=requeue)
