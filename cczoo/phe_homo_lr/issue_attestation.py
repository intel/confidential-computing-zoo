import grpc
import os
import sys

from hetero_attestation_pb2 import RegisterNodeRequest
from hetero_attestation_pb2 import RegisterNodeResponse
from hetero_attestation_pb2 import HeteroAttestationRequest
from hetero_attestation_pb2 import HeteroAttestationResponse
from hetero_attestation_pb2 import TeeAttestationRequest
from hetero_attestation_pb2 import TeeAttestationResponse
from hetero_attestation_pb2 import RunStatus
from hetero_attestation_pb2_grpc import TeeNodeService 
import hetero_attestation_pb2_grpc

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.x509 import load_pem_x509_certificate
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature
import cryptography.hazmat.backends as backends
from datetime import datetime, timedelta

import logging
logging.basicConfig(level=logging.DEBUG,
                    format="[%(asctime)s][%(name)s][%(levelname)s] %(message)s",
                    datefmt = '%Y-%m-%d  %H:%M:%S %a'
                    )

class HeteroAttestationIssuer:
    def __init__(self, ca_cert_path, attest_id, node_id, tee_node_addr, nonce):
        self.attest_id = attest_id
        self.node_id = node_id
        self.tee_node_addr = tee_node_addr
        self.nonce = nonce
        self.ca_cert_path = ca_cert_path

    def CheckSignature(self, message, signature):
        with open(self.ca_cert_path, "rb") as f:
            ca_cert_bytes = f.read()

        ca_cert = load_pem_x509_certificate(ca_cert_bytes, default_backend())
        public_key = ca_cert.public_key()

        try:
            public_key.verify(signature, message,
                              padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                          salt_length=padding.PSS.MAX_LENGTH),
                              hashes.SHA256())
            return True
        except InvalidSignature:
            return False

    def IssueHeteroAttestation(self):
        channel = grpc.insecure_channel(self.tee_node_addr)
        stub = hetero_attestation_pb2_grpc.TransmitServiceStub(channel)

        request = HeteroAttestationRequest(attest_id = self.attest_id,
                                           nonce = self.nonce,
                                           node_id = self.node_id)

        response = stub.TransmitAttestationRequest(request)
        if response.status.error == True:
            logging.error(f"Error from {self.tee_node_addr}: {response.status.msg}")
            return False

        proof = response.tee_proof
        verify_result = response.verify_result
        signature = bytes.fromhex(response.signature)

        message = response.tee_proof + response.verify_result + self.nonce.hex()
        message = message.encode("utf-8")

        if response.nonce.hex() != self.nonce.hex():
            logging.error("Nonce mismatch error.")
            return False

        if not self.CheckSignature(message, signature):
            logging.error("Verify signature failed.")
            return False
        else:
            logging.info("Verify signature finish.")

        if verify_result == "pass":
            logging.info("Verify passed.")
            return True
        else:
            logging.error("Verify failed.")
            return False
