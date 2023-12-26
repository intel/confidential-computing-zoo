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
import grpc
import os
import sys
import secrets
import numpy as np
import pandas as pd
from concurrent.futures import ThreadPoolExecutor as Executor
from ipcl_python import PaillierKeypair
import homo_lr_pb2
import homo_lr_pb2_grpc
from hetero_attestation_pb2 import TargetInfoRequest
from hetero_attestation_pb2 import TargetInfoResponse
from hetero_attestation_pb2 import HeteroAttestationRequest
import hetero_attestation_pb2_grpc

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
    self.pub_key, self.pri_key = PaillierKeypair.generate_keypair(key_length)

  def get_pubkey(self):
    return self.pub_key

  def get_prikey(self):
    return self.pri_key

  def aggregate_model(self, iter_n, weights):
    if iter_n in self.weights_dict:
      self.weights_dict[iter_n].append(weights)
    else:
      self.weights_dict[iter_n]=[weights]
    while len(self.weights_dict[iter_n]) < self.worker_num:
      continue
    self.updated_weights = (1 / self.worker_num) * np.sum(self.weights_dict[iter_n], axis=0)
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
    x = np.concatenate((np.ones((m,1)),x), axis = 1)
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
      loss = (-1/m) * np.sum((np.multiply(y, np.log(y_pred)) + np.multiply((1 - y), np.log(1 - y_pred))))
    y_pred[y_pred < 0.5] = 0
    y_pred[y_pred >= 0.5] = 1
    acc = np.sum(y_pred == y) / m
    return acc, loss

  def sigmoid(self, x):
    return 1 / (1 + np.exp(-x))

class AggregateServicer(homo_lr_pb2_grpc.HostServicer):
    def __init__(self, key_length, worker_num, validate_set, secure):
      self.host = HomoLRHost(key_length, worker_num, secure)
      self.dataset = validate_set
      self.worker_num = worker_num
      self.finished = 0

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
        server.stop(5)
      return homo_lr_pb2.Empty()

def parse_dataset(dataset):
  data_array = pd.read_csv(dataset).to_numpy()
  x = data_array[:, 2:]
  y = data_array[:, 1].astype('int32')
  return x, y

class HeteroAttestationTransmit(hetero_attestation_pb2_grpc.TransmitService):
    def TransmitAttestationRequest(self, request):
        # 1.Request the qe_target_info. 
        channel = grpc.insecure_channel("172.21.1.64:40070")
        stub = hetero_attestation_pb2_grpc.TargetInfoServiceStub(channel)
        target_info_request = TargetInfoRequest(name = "homo_lr_in_gramine")
        target_info_response = stub.GetQETargetInfo(target_info_request)
        target_info = target_info_response.qe_target_info

        # 2.Generate SGX report.
        fd = os.open("/dev/attestation/target_info", os.O_WRONLY)
        os.write(fd, target_info)
        
        nonce = secrets.token_bytes(nbytes = 10)
        print(nonce.hex(), file = sys.stderr, flush = True)

        fd = os.open("/dev/attestation/user_report_data", os.O_WRONLY)
        os.write(fd, nonce)
        
        fd = os.open("/dev/attestation/report", os.O_RDONLY)
        report = os.read(fd, 432)

        # 3.Issue quote generation and verificatin to SGX node service.
        request.report = report
        stub = hetero_attestation_pb2_grpc.TeeNodeServiceStub()
        response = stub.IssueRemoteAttestation(request)

        # 4.Return verification result without any check.
        return response

# def run_attestation():
#     # 1.Request the qe_target_info. 
#     channel = grpc.insecure_channel("172.21.1.64:40070")
#     stub = hetero_attestation_pb2_grpc.TargetInfoServiceStub(channel)
#     target_info_request = TargetInfoRequest(name = "homo_lr_in_gramine")
#     target_info_response = stub.GetQETargetInfo(target_info_request)
#     target_info = target_info_response.qe_target_info
# 
#     # 2.Generate SGX report.
#     fd = os.open("/dev/attestation/target_info", os.O_WRONLY)
#     os.write(fd, target_info)
#     
#     nonce = secrets.token_bytes(nbytes = 10)
#     print(nonce.hex(), file = sys.stderr, flush = True)
# 
#     fd = os.open("/dev/attestation/user_report_data", os.O_WRONLY)
#     os.write(fd, nonce)
#     
#     fd = os.open("/dev/attestation/report", os.O_RDONLY)
#     report = os.read(fd, 432)
# 
#     # 3.Issue quote generation and verificatin to SGX node service.
#     request = HeteroAttestationRequest(attest_id = "test", 
#                                        nonce = "test".encode("utf-8"), 
#                                        node_id = "gramine", 
#                                        report = report)
#     stub = hetero_attestation_pb2_grpc.TeeNodeServiceStub(channel)
#     response = stub.IssueRemoteAttestation(request)
#     print(response, file = sys.stderr, flush = True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--key-length', type=int, default=1024, help='Bit length of PHE key')
    parser.add_argument('--worker-num', type=int, required=True, help='The numbers of workers in HFL')
    parser.add_argument('--validate-set', help='CSV format validation data')
    parser.add_argument('--secure', default=True, help='Enable PHE or not')
    args = parser.parse_args()
    
    server = grpc.server(Executor(max_workers=10))
    servicer = AggregateServicer(args.key_length, args.worker_num, args.validate_set, args.secure)
    homo_lr_pb2_grpc.add_HostServicer_to_server(servicer, server)

    servicer = HeteroAttestationTransmit()
    hetero_attestation_pb2_grpc.add_TransmitServiceServicer_to_server(servicer, server)

    server.add_insecure_port('[::]:50051')
    server.start()
    server.wait_for_termination()
