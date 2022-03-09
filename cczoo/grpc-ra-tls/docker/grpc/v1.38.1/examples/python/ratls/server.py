#
# Copyright (c) 2022 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""The Python implementation of the GRPC ratls.Greeter server."""

from concurrent import futures
import logging
import argparse

import grpc

import ratls_pb2
import ratls_pb2_grpc


class Greeter(ratls_pb2_grpc.GreeterServicer):
    def SayHello(self, request, context):
        return ratls_pb2.HelloReply(message='Hello, %s!' % request.name)

def serve(args):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    ratls_pb2_grpc.add_GreeterServicer_to_server(Greeter(), server)

    credentials = grpc.sgxratls_server_credentials(config_json=args.config)
    server.add_secure_port(args.host, credentials)

    server.start()
    server.wait_for_termination()

def command_arguments():
    parser = argparse.ArgumentParser(description='GRPC client.')
    parser.add_argument(
        '-host',
        '--host',
        type=str,
        required=False,
        default='localhost:50051',
        help='The server socket address.'
    )
    parser.add_argument(
        '-config',
        '--config',
        type=str,
        required=False,
        default='dynamic_config.json',
        help='The path of dynamic config json'
    )
    return parser.parse_args()

if __name__ == '__main__':
    args = command_arguments()
    logging.basicConfig()
    serve(args)
