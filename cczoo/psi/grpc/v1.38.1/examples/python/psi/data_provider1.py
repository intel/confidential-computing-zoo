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


from __future__ import print_function
import logging
import argparse

import grpc

import psi_pb2
import psi_pb2_grpc

import os


def run(args, data, client_name):
    credentials = grpc.sgxratls_channel_credentials(
        config_json=args.config, verify_option="two-way")
    channel = grpc.secure_channel(args.host, credentials)
    stub = psi_pb2_grpc.PSIStub(channel)

    remote_attestation = stub.RemoteAttestation(psi_pb2.RARequest(name=data[0]))
    print("PSI client received: ", remote_attestation.message)

    connect = stub.Connect(psi_pb2.ConnectRequest(client_name=client_name, is_chief=args.is_chief, client_num=args.client_num))
    print(connect.message)

    data_upload = stub.DataUpload(psi_pb2.DataUploadRequest(input_data=data))
    print(data_upload.message)

    cal_psi = stub.CalPsi(psi_pb2.CalPsiRequest(client_name=client_name))
    print(cal_psi.data)

    channel.close()

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
        help='The path of dynamic config json.'
    )
    parser.add_argument(
        '-is_chief',
        '--is_chief',
        type=bool,
        required=False,
        default='False',
        help='The chief client or not.'
    )
    parser.add_argument(
        '-data_dir',
        '--data_dir',
        type=str,
        required=True,
        default='data.txt',
        help='The data directory to upload.'
    )
    parser.add_argument(
        '-client_num',
        '--client_num',
        type=int,
        required=True,
        default=2,
        help='The total client number.'
    )
    return parser.parse_args()

def load_data():
    data = []
    with open(args.data_dir, 'r') as f:
        for line in f:
            data.append(line.strip())
    return data

if __name__ == '__main__':
    args = command_arguments()
    logging.basicConfig()
    data = load_data()
    client_name = os.path.basename(__file__).split('.')[0]
    run(args, data, client_name)
