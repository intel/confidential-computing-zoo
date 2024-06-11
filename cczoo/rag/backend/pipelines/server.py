import os
import json
from pathlib import Path

import grpc
import query_pb2, query_pb2_grpc
from concurrent.futures import ThreadPoolExecutor

from haystack import Pipeline
from haystack.nodes.prompt import PromptNode


query_pipeline = Pipeline.load_from_yaml(Path("rag.yaml"))

def _get_grpc_streaming_iterator(pipeline, request=None):
    params = request["params"] or {}
    components = pipeline.components
    node_name = None
    iterator = None
    for name in components.keys():
        if isinstance(components[name], PromptNode):
            node_name = name
    if node_name != None:
        streaming_param = {"stream": True, "return_iterator": True}
        params[node_name].update(streaming_param)
        # only one streaming iterator is support for rest_api
        iterator = pipeline.run(query=request["query"], params=params)["iterator"][0]
    return iterator

class QueryServicer(query_pb2_grpc.QueryServicer):

    def UnaryStream(self, request, context):
        request = json.loads(request.msg)
        iterator = _get_grpc_streaming_iterator(query_pipeline, request)
        for iter in iterator:
            yield query_pb2.Response(msg=iter)

    def Status(self, request, context):
        return query_pb2.Response(msg=request.msg)

API_ENDPOINT_GRPC = os.getenv("API_ENDPOINT_GRPC", "[::]:80")
API_PROTOCOL = os.getenv("API_PROTOCOL", "grpc")
print("API_PROTOCOL:", API_PROTOCOL, flush=True)

server = grpc.server(ThreadPoolExecutor(max_workers=8))
query_pb2_grpc.add_QueryServicer_to_server(QueryServicer(), server)

if API_PROTOCOL == "grpc-ratls":
    credentials = grpc.sgxratls_server_credentials(
        config_json="dynamic_config.json", verify_option="two-way")
    server.add_secure_port(API_ENDPOINT_GRPC, credentials)
else:
    server.add_insecure_port(API_ENDPOINT_GRPC)

server.start()
server.wait_for_termination()
