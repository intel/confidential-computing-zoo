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




+-------------------------------------------------------------------------------------------------------------------------------------------+-----------------------+-------------+------------------------------------------------------------------------+---------------------------------------------------------------------------------------------------------+
|                                               Solutions                                                                                   |                       |             |                                                                        |            Security Technologies                                                                        |
|                                                                                                                                           |    Key Applications   |   Status    |  Validated In Public Cloud                                             +----------+-------+---------+--------------------+-----------------------+---------------------+---------+
|                                                                                                                                           |                       |             |                                                                        |   TEE    |  HE   |  LibOS  | Remote Attestation | Encryption/Decryption | CPU HW Acceleration |   TLS   |
+===========================================================================================================================================+=======================+=============+========================================================================+==========+=======+=========+====================+=======================+=====================+=========+
| `TensorFlow Serving Cluster PPML based on SGX <https://cczoo.readthedocs.io/en/latest/Solutions/tensorflow-serving-cluster/index.html>`__ |    TensorFlow, K8S    |  Published  |  `Aliyun ECS <https://help.aliyun.com/document_detail/342755.html>`__  |  SGX     | /     |  Gramine|   YES              |   YES                 |  /                  | gRPC    |
+-------------------------------------------------------------------------------------------------------------------------------------------+-----------------------+-------------+------------------------------------------------------------------------+----------+-------+---------+--------------------+-----------------------+---------------------+---------+
| `Horizontal Federal Learning <https://cczoo.readthedocs.io/en/latest/Solutions/horizontal-federated-learning/hfl.html>`__                 |     TensorFlow        |  Published  |  /                                                                     |  SGX     | /     |  Gramine|   2-way RA-TLS     |   YES                 |  /                  | gRPC    |
+-------------------------------------------------------------------------------------------------------------------------------------------+-----------------------+-------------+------------------------------------------------------------------------+----------+-------+---------+--------------------+-----------------------+---------------------+---------+
| Vertical Federal Learning based on SGX                                                                                                    |     TensorFlow        |  In Progress|  /                                                                     |  SGX     | /     |  Gramine|   2-way RA-TLS     |   YES                 |  /                  | gRPC    |
+-------------------------------------------------------------------------------------------------------------------------------------------+-----------------------+-------------+------------------------------------------------------------------------+----------+-------+---------+--------------------+-----------------------+---------------------+---------+
| Leveled HE logical regression inference                                                                                                   |     /                 |  In Progress|  /                                                                     |  /       |Pailler|  /      |   /                |   YES                 |  /                  | /       |
+-------------------------------------------------------------------------------------------------------------------------------------------+-----------------------+-------------+------------------------------------------------------------------------+----------+-------+---------+--------------------+-----------------------+---------------------+---------+
| FATE Paillier logical regression+optimization                                                                                             |     /                 |  In Progress|  /                                                                     |  /       |  HE   |  /      |   /                |   YES                 |  /                  | /       |
+-------------------------------------------------------------------------------------------------------------------------------------------+-----------------------+-------------+------------------------------------------------------------------------+----------+-------+---------+--------------------+-----------------------+---------------------+---------+
| MPC Optimization                                                                                                                          |     /                 |  Not Start  |  /                                                                     |  /       |  HE   |  /      |   /                |   YES                 |  /                  | /       |
+-------------------------------------------------------------------------------------------------------------------------------------------+-----------------------+-------------+------------------------------------------------------------------------+----------+-------+---------+--------------------+-----------------------+---------------------+---------+
| gRPC supporting Intel RA-TLS                                                                                                              |     /                 |  In Progress|  /                                                                     |  SGX/TDX | /     |  /      |   2-way RA-TLS     |   /                   |  /                  | gRPC    |
+-------------------------------------------------------------------------------------------------------------------------------------------+-----------------------+-------------+------------------------------------------------------------------------+----------+-------+---------+--------------------+-----------------------+---------------------+---------+
| Attestation Server & KMS                                                                                                                  |     /                 |  Not Start  |  /                                                                     |  SGX/TDX | /     |  /      |   YES              |   YES                 |  /                  | /       |
+-------------------------------------------------------------------------------------------------------------------------------------------+-----------------------+-------------+------------------------------------------------------------------------+----------+-------+---------+--------------------+-----------------------+---------------------+---------+
| Secure BigDL Recommend system                                                                                                             |     /                 |  Not Start  |  /                                                                     |  SGX     | /     |  /      |   YES              |   YES                 |  /                  | /       |
+-------------------------------------------------------------------------------------------------------------------------------------------+-----------------------+-------------+------------------------------------------------------------------------+----------+-------+---------+--------------------+-----------------------+---------------------+---------+


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

.. toctree::
   :maxdepth: 1
   :caption: LibOS Introduction

   LibOS/libos.md
