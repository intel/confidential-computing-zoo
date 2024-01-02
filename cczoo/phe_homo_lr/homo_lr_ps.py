#
# Copyright (c) 2021 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pickle
import argparse
import time
import grpc
import os
import sys
import secrets
import numpy as np
import pandas as pd
import threading
from concurrent.futures import ThreadPoolExecutor as Executor
from ipcl_python import PaillierKeypair
import homo_lr_pb2
import homo_lr_pb2_grpc
import hetero_attestation_pb2_grpc
import logging

from attestation import HeteroAttestationTransmit
from attestation import HeteroAttestationIssuer

logging.basicConfig(level=logging.DEBUG,
                    format="[%(asctime)s][%(name)s][%(levelname)s] %(message)s",
                    datefmt='%Y-%m-%d  %H:%M:%S %a')

class HomoLRHost(object):
    def __init__(self, key_length, worker_num, secure):
        self.worker_num = worker_num
        self.weights_dict = {}
        self.updated_weights = None
        self.secure = secure
        self.pub_key = None
        self.pri_key = None
        if secure:
            self.generate_key(key_length)

    def generate_key(self, key_length=1024):
        self.pub_key, self.pri_key = PaillierKeypair.generate_keypair(
            key_length)

    def get_pubkey(self):
        return self.pub_key

    def get_prikey(self):
        return self.pri_key

    def aggregate_model(self, iter_n, weights):
        if iter_n in self.weights_dict:
            self.weights_dict[iter_n].append(weights)
        else:
            self.weights_dict[iter_n] = [weights]
        while len(self.weights_dict[iter_n]) < self.worker_num:
            continue
        self.updated_weights = (1 / self.worker_num) * \
            np.sum(self.weights_dict[iter_n], axis=0)
        if self.secure:
            self.updated_weights = self.re_encrypt(self.updated_weights)
        return self.updated_weights

    def re_encrypt(self, values):
        n = values.shape[1]
        values = values.flatten()
        ret = []
        for i in range(n):
            pt = self.pri_key.decrypt(values[i])
            ret.append(self.pub_key.encrypt(pt))
        return np.array(ret)

    def validate(self, x, y):
        w = None
        m = x.shape[0]
        x = np.concatenate((np.ones((m, 1)), x), axis=1)
        n = x.shape[1]
        loss = np.nan
        if self.secure:
            w = []
            for i in range(n):
                w.append(self.pri_key.decrypt(self.updated_weights[i]))
            w = np.array(w)
        else:
            w = self.updated_weights.flatten()
        y_pred = self.sigmoid(np.dot(x, w))
        if not (0 in y_pred or 1 in y_pred):
            loss = (-1/m) * np.sum((np.multiply(y, np.log(y_pred)) +
                                    np.multiply((1 - y), np.log(1 - y_pred))))
        y_pred[y_pred < 0.5] = 0
        y_pred[y_pred >= 0.5] = 1
        acc = np.sum(y_pred == y) / m
        return acc, loss

    def sigmoid(self, x):
        return 1 / (1 + np.exp(-x))


class AggregateServicer(homo_lr_pb2_grpc.HostServicer):
    def __init__(self, key_length, worker_num, validate_set, secure, server):
        self.host = HomoLRHost(key_length, worker_num, secure)
        self.dataset = validate_set
        self.worker_num = worker_num
        self.finished = 0
        self.server = server

    def GetPubKey(self, request, context):
        pubkey = pickle.dumps(self.host.get_pubkey())
        return homo_lr_pb2.KeyReply(key=pubkey)

    def AggregateModel(self, request, context):
        weights = pickle.loads(request.weights)
        updated_weights = self.host.aggregate_model(request.iter_n, weights)
        updated_w_pb = pickle.dumps(updated_weights)
        return homo_lr_pb2.WeightsReply(updated_weights=updated_w_pb)

    def Validate(self, request, context):
        if self.dataset is not None:
            x, y = parse_dataset(self.dataset)
            accuracy, loss = self.host.validate(x, y)
            return homo_lr_pb2.ValidateReply(acc=accuracy, loss=loss)
        else:
            return homo_lr_pb2.ValidateReply(acc=0, loss=0)

    def Finish(self, request, context):
        self.finished += 1
        if self.finished == self.worker_num:
            self.server.stop(5)
        return homo_lr_pb2.Empty()

    def Alive(self, request, context):
        return homo_lr_pb2.Empty()

def parse_dataset(dataset):
    data_array = pd.read_csv(dataset).to_numpy()
    x = data_array[:, 2:]
    y = data_array[:, 1].astype('int32')
    return x, y

def check_peer_alive(peer_addr, peer_name, retry_time):
    while True:
        try:
            channel = grpc.insecure_channel(peer_addr)
            stub = homo_lr_pb2_grpc.HostStub(channel)

            request = homo_lr_pb2.Empty()
            response = stub.Alive(request)
        except Exception as e:
            time.sleep(retry_time)
            logging.info(f"Peer {peer_name} is not online.")
            continue

        logging.info(f"Peer {peer_name} is online.")
        break


def verify_party(peer_addr, peer_name, attest_id, node_id):
    check_peer_alive(peer_addr, peer_name, 5)
    nonce = secrets.token_bytes(10)
    issuer = HeteroAttestationIssuer("/key/ca_cert",
                                     attest_id, node_id,
                                     peer_addr, nonce)

    if not issuer.IssueHeteroAttestation():
        raise RuntimeError("{} is not trusted.".format(peer_name))
    else:
        logging.info("{} is trusted.".format(peer_name))


def run_server(args):
    server = grpc.server(Executor(max_workers=10))
    servicer = AggregateServicer(
        args.key_length, args.worker_num, args.validate_set, args.secure, server)
    homo_lr_pb2_grpc.add_HostServicer_to_server(servicer, server)

    servicer = HeteroAttestationTransmit("172.21.1.64:40070")
    hetero_attestation_pb2_grpc.add_TransmitServiceServicer_to_server(
        servicer, server)

    server.add_insecure_port('[::]:50051')
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--key-length', type=int,
                        default=1024, help='Bit length of PHE key')
    parser.add_argument('--worker-num', type=int, required=True,
                        help='The numbers of workers in HFL')
    parser.add_argument('--validate-set', help='CSV format validation data')
    parser.add_argument('--secure', default=False, help='Enable PHE or not')
    args = parser.parse_args()

    verify_party("172.21.1.65:60051", "party_1",
                 "RA_from_gramine_ps", "ps_in_gramine")
    verify_party("172.21.1.65:60052", "party_1",
                 "RA_from_gramine_ps", "ps_in_gramine")

    thread = threading.Thread(target=run_server, args=(args,))
    thread.start()
    
    thread.join()
