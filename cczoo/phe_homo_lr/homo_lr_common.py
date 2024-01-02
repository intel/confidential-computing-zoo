import logging
import grpc
import secrets
import homo_lr_pb2
import homo_lr_pb2_grpc
import json
import time
from attestation import HeteroAttestationTransmit
from attestation import HeteroAttestationIssuer

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


def parse_config(config_path):
    with open(config_path , "r") as f:
        config = json.load(f)
    
    attest_addr = config["attestation_service"]
    ps_addr = config["party_service"]["ps"]
    worker_1_addr = config["party_service"]["1"]
    worker_2_addr = config["party_service"]["2"]

    logging.info(f"Attestation service of local: {attest_addr}.")
    logging.info(f"Party service of PS: {ps_addr}.")
    logging.info(f"Party service of worker 1: {worker_1_addr}.")
    logging.info(f"Party service of worker 2: {worker_2_addr}.")

    return config
