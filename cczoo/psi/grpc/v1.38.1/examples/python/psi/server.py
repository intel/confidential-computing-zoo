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


from concurrent import futures
import logging
import argparse

import grpc

import psi_pb2
import psi_pb2_grpc

import time

from collections import Counter

class PSI(psi_pb2_grpc.PSIServicer):
    def __init__(self):
        self.cur_client_num = 0
        self.chief = ""
        self.data = []
        self.results = []

    def RemoteAttestation(self, request, context):
        return psi_pb2.RAReply(message='Remote attestation succeed!')

    def Connect(self, request, context):
        self.cur_client_num += 1
        if request.is_chief == True:
            self.chief = request.client_name
        print("current client number: %s." % self.cur_client_num)
        if request.client_name != "" and request.client_name == self.chief:
            print("Connect %s successfully." % request.client_name)
            while True:
                if request.client_num == self.cur_client_num:
                    return psi_pb2.ConnectReply(message="All client connect successfully")
        else:
            print("Connect %s successfully." % request.client_name)
            return psi_pb2.ConnectReply(mesage="Connect successfully.")

    def DataUpload(self, request, context):
        tmp_data = []
        if len(request.input_data) == 0:
            return psi_pb2.UploadReply(message="Please update your data correctly.")
        for i in range(len(request.input_data)):
            tmp_data.append(request.input_data[i])
        self.data.append(tmp_data)
        return psi_pb2.UploadReply(message="Data uploaded.")

    def CalPsi(self, request, context):
        if request.client_name != "" and request.client_name == self.chief:
            while True:
                all_uploaded = True
                for i in range(0, self.cur_client_num):
                    if len(self.data[i]) == 0:
                        all_uploaded = False
                if all_uploaded:
                    break
            if self.cur_client_num == 2:
                data1 = self.data[0]
                data2 = self.data[1]
                data1.sort()
                data2.sort()
                length1, length2 = len(data1), len(data2)
                index1 = index2 = 0
                while index1 < length1 and index2 < length2:
                    num1 = data1[index1]
                    num2 = data2[index2]
                    if num1 == num2:
                        if not self.results or num1 != self.results[-1]:
                            self.results.append(num1)
                        index1 += 1
                        index2 += 1
                    elif num1 < num2:
                        index1 += 1
                    else:
                        index2 += 1
                return psi_pb2.Results(data=self.results)
            elif self.cur_client_num >= 3:
                data = []
                for i in range(len(self.data)):
                    data += self.data[i]
                counter = Counter(data)
                for key, value in counter.items():
                    if value == self.cur_client_num:
                        self.results.append(key)
                return psi_pb2.Results(data=self.results)
        else:
            while True:
                if self.results != []:
                    return psi_pb2.Results(data=self.results)


def serve(args):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    psi_pb2_grpc.add_PSIServicer_to_server(PSI(), server)
    psi_pb2_grpc.add_PSIServicer_to_server(PSI(), server)

    credentials = grpc.sgxratls_server_credentials(
        config_json=args.config, verify_option="two-way")
    server.add_secure_port(args.host, credentials)

    server.start()

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        grpc_server.stop(0)

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
