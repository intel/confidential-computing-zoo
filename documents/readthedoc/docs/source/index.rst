Welcome to Confidential Computing Zoo's documentation!
======================================================

Confidential Computing Zoo (CCZoo) is a collection of code-ready reference solutions, which can be used as a copy-paste developer guide, demonstrating how to apply modern
security technologies to real-life cloud business scenarios, in order to facilitate the developers to build their own end-to-end Confidential Computing solutions more easily.
Some of the solutions are also validated on the public cloud services, such as Alibaba Cloud, AWS, Azure, etc.

The concerned modern security technologies are (but not limited to): TEE (Trusted Execution Environment, such as Intel® SGX and TDX), HE (Homomorphic Encryption) and its
hardware accelerations, Remote Attestation, LibOS, cryptographic and its hardware accelerations. The concerned business scenarios are (but not limited to): cloud native AI
inference, vertical and horizontal federated learning, big data analytics, key management, RPC (Remote Process Call, such as gRPC), etc.

CCZoo maintains a live table, as below, to indicate the correlations between business usages (rows) and security technologies (columns). Each hyperlink will direct you to the
document section that explains the corresponding details and then guides you to the source codes. Enjoy!

CCZoo is a growing project and we have a growing contributor and maintainer community.
Please submit issues in this project if there is any question or request.
Welcome PRs for contributions.


*****************
Table of Contents
*****************

.. toctree::
   :maxdepth: 1
   :caption: Solution Deployment

   Solutions/tensorflow-serving-cluster/index.rst
   Solutions/horizontal-federated-learning/hfl.md
   Solutions/vertical-federated-learning/vfl.md
   Solutions/grpc-ra-tls/index.md
   Solutions/ehsm-kms/index.md
   Solutions/rats-tls/index.md
   Solutions/cross_language_framework_based_gramine/Readme.md
   Solutions/attestation-secret-provision/index.md
   Solutions/logistic-regression-inference-HE-SGX/index.md
   Solutions/bigdl-ppml/index.md
   Solutions/phe_homo_lr/phe_homo_lr.md
   Solutions/psi/PSI.md
   Solutions/httpa/index.md
   Solutions/tdx-hfl/tdx-hfl.md
   Solutions/hfl-tdx-coco/index.md
   Solutions/tdx-encrypted-vfs/index.md
   Solutions/td-encrypted-img/index.md
   Solutions/tdx-tf-serving-ppml/index.md
   Solutions/td-encrypte-img/index.md

.. toctree::
   :maxdepth: 1
   :caption: Cloud Deployment

   Cloud/cloudDeployment.md

.. toctree::
   :maxdepth: 1
   :caption: Penetration Testing

   Pentests/Overview.md
   Pentests/unauthorized_access/redis/index.md
   Pentests/memory_attack/sgx/key_generator/index.md

.. toctree::
   :maxdepth: 1
   :caption: LibOS Introduction

   LibOS/libos.md


.. toctree::
   :maxdepth: 1
   :caption: TDX Introduction

   TEE/TDX/inteltdx.md
   TEE/TDX/tdxstack.md
   TEE/TDX/tdxcoco.md 

