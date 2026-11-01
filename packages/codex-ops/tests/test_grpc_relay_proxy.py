import os
from pathlib import Path
import subprocess
import sys
import unittest


class RelayProxyTests(unittest.TestCase):
    def test_loopback_relay_ignores_http_proxy(self):
        bridge = Path(__file__).resolve().parents[1] / 'runtime_bridge'
        script = '''
import concurrent.futures, grpc, sys
sys.path.insert(0, sys.argv[1])
from grpc_relay import serve
server = grpc.server(concurrent.futures.ThreadPoolExecutor(max_workers=2))
handler = grpc.stream_stream_rpc_method_handler(lambda requests, context: requests)
server.add_generic_rpc_handlers([grpc.method_handlers_generic_handler('test.Echo', {'Call': handler})])
port = server.add_insecure_port('127.0.0.1:0')
server.start()
relay, upstream, state, relay_port = serve(f'127.0.0.1:{port}', enabled=False)
channel = grpc.insecure_channel(f'127.0.0.1:{relay_port}', options=[('grpc.enable_http_proxy', 0)])
try:
    assert list(channel.stream_stream('/test.Echo/Call')(iter([b'unchanged']), timeout=5)) == [b'unchanged']
finally:
    channel.close()
    relay.stop(0)
    upstream.close()
    state.close()
    server.stop(0)
'''
        env = {key: value for key, value in os.environ.items()
               if key.lower() not in ('http_proxy', 'https_proxy', 'all_proxy', 'no_proxy')}
        env['http_proxy'] = 'http://127.0.0.1:1'
        result = subprocess.run([sys.executable, '-c', script, str(bridge)], env=env,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
