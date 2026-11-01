"""Loopback-only opaque gRPC relay with an outbound presentation projection."""
import concurrent.futures
import threading

import grpc
from projection import project
from store import Store
from presentation_policy import Presenter
from telemetry import Telemetry
from bridge_context import context as attribution

OPTIONS = [('grpc.max_receive_message_length', 67108864), ('grpc.max_send_message_length', 67108864)]


class Relay(grpc.GenericRpcHandler):
    def __init__(self, upstream, on_frame=None, enabled=True):
        self.upstream = upstream
        self.on_frame = on_frame
        self.enabled = enabled
        self.telemetry = Telemetry()
        self.presenter = Presenter(observer=self.telemetry.record)
        self.lock = threading.Lock()
        self.counts = {'inboundFrames': 0, 'outboundFrames': 0, 'compactedFrames': 0, 'originalBytes': 0, 'presentedBytes': 0}

    def close(self):
        self.telemetry.close()

    def service(self, details):
        method = details.method
        def forward(requests, context):
            labels = attribution(method, b'')
            presenter = self._presenter(labels)
            def inbound():
                for data in requests:
                    labels.clear()
                    labels.update(attribution(method, data))
                    with self.lock:
                        self.counts['inboundFrames'] += 1
                    if self.on_frame:
                        self.on_frame('to_host', method, data, data)
                    yield data  # CompleteToolCall and all client requests are byte-identical.
            call = self.upstream.stream_stream(method)(inbound(), metadata=context.invocation_metadata())
            context.add_callback(call.cancel)
            try:
                # Long-lived subscriptions must get headers before the first event.
                context.send_initial_metadata(call.initial_metadata())
                for data in call:
                    displayed = project(method, data, presenter) if self.enabled else data
                    with self.lock:
                        self.counts['outboundFrames'] += 1
                        self.counts['compactedFrames'] += int(displayed != data)
                        self.counts['originalBytes'] += len(data)
                        self.counts['presentedBytes'] += len(displayed)
                    if self.on_frame:
                        self.on_frame('from_host', method, data, displayed)
                    yield displayed
                context.set_trailing_metadata(call.trailing_metadata())
            except grpc.RpcError as exc:
                context.abort(exc.code(), exc.details())
            finally:
                call.cancel()
        return grpc.stream_stream_rpc_method_handler(forward, request_deserializer=lambda b: b, response_serializer=lambda b: b)

    def _presenter(self, labels):
        return Presenter(progress=self.presenter.progress,
            observer=lambda channel, reason, before, after: self.telemetry.record(channel, reason, before, after, dict(labels)),
            on_reference=lambda ref: self.telemetry.link_reference(ref, dict(labels)))


def serve(upstream_address, port=0, on_frame=None, enabled=True):
    # Initialize before concurrent notification/result streams open connections.
    # If storage is unavailable, presentation.compact keeps the original text.
    if enabled:
        try:
            initial = Store()
            initial.close()
        except Exception:
            pass
    channel = grpc.insecure_channel(upstream_address, options=OPTIONS)
    grpc.channel_ready_future(channel).result(timeout=10)
    relay = Relay(channel, on_frame, enabled)
    server = grpc.server(concurrent.futures.ThreadPoolExecutor(max_workers=64), options=OPTIONS)
    server.add_generic_rpc_handlers([relay])
    bound = server.add_insecure_port(f'127.0.0.1:{port}')
    if not bound:
        channel.close()
        raise RuntimeError('Cannot bind loopback relay')
    server.start()
    return server, channel, relay, bound
