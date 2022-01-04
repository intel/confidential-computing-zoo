<div align="center">

<p align="center"> <img src="documents/readthedoc/docs/source/Images/cczoo.jpg" height="140px"><br></p>

</div>

Confidential Computing Zoo (CCZoo) is a collection of code-ready reference solutions, which can be used as a copy-paste developer guide, demonstrating how to apply modern
security technologies to real-life cloud business scenarios, in order to facilitate the developers to build their own end-to-end Confidential Computing solutions more easily.
Some of the solutions are also validated on the public cloud services, such as Alibaba Cloud, AWS, Azure, etc.

The concerned modern security technologies are (but not limited to): TEE (Trusted Execution Environment, such as Intel® SGX and TDX), HE (Homomorphic Encryption) and its
hardware accelerations, Remote Attestation, LibOS, cryptographic and its hardware accelerations. The concerned business scenarios are (but not limited to): cloud native AI
inference, vertical and horizontal federated learning, big data analytics, key management, RPC (Remote Process Call, such as gRPC), etc.

CCZoo maintains a live table, as below, to indicate the correlations between business usages (rows) and security technologies (columns). Each hyperlink will direct you to the
document section that explains the corresponding details and then guides you to the source codes. Enjoy!

# Confidential Computing Zoo Solution Table

| Solutions                                                    | Cloud  Deployment                                            | TEE     | HE       | Application        | LibOS   | Remote Attestation                                           | Encryption /Decryption | CPU HW Acceleration | TLS  | Status        |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ------- | -------- | ------------------ | ------- | ------------------------------------------------------------ | ---------------------- | ------------------- | ---- | ------------- |
| [TensorFlow Serving Cluster PPML based on SGX](https://cczoo.readthedocs.io/en/latest/Solutions/tensorflow-serving-cluster/index.html) | [Aliyun ECS](https://help.aliyun.com/document_detail/342755.html) | SGX     | -        | TensorFlow Serving | Gramine | [Secret Provinsion Service](https://cczoo.readthedocs.io/en/latest/Solutions/tensorflow-serving-cluster/index.html#start-secret-provision-service) | Yes                    | -                   | gRPC | **Published** |
| Vertical Federal Learning based on SGX                       | -                                                            | SGX     | -        | TensorFlow         | Gramine | 2-way RA-TLS                                                 | Yes                    | -                   | gRPC | In progress   |
| [Horizontal Federal Learning](https://cczoo.readthedocs.io/en/latest/Solutions/horizontal-federated-learning/hfl.html)                                  | -                                                            | SGX     | -        | TensorFlow         | Gramine | 2-way RA-TLS                                                 | Yes                    | -                   | gRPC | In progress   |
| FATE Paillier logical regression+optimization                | -                                                            | -       | Paillier | -                  | -       | -                                                            | Yes                    | -                   | -    | In progress   |
| Leveled HE logical regression inference                      | -                                                            | -       | HE       | -                  | -       | -                                                            | Yes                    | -                   | -    | In progress   |
| MPC Optimization                                             | -                                                            | -       | HE       | -                  | -       | -                                                            | -                      | -                   | -    | Not Start     |
| gRPC supporting Intel RA-TLS                                 | -                                                            | SGX/TDX | -        | -                  | -       | Yes                                                          | Yes                    | -                   | gRPC | In progress   |
| Attestation Server & KMS                                     | -                                                            | SGX/TDX | -        | -                  | -       | -                                                            | -                      | -                   | -    | Not Start     |
| Secure BigDL Recommend system                                | -                                                            | SGX     | -        | -                  | -       | -                                                            | -                      | -                   | -    | Not Start     |

---
There are some high barriers for users to adopt Intel TEE directly. For example, the implementation of Intel SGX and TDX run through a deep stack, from hardware, firmware to software, to guarantee the final runtime security. To better understand the design of SGX and TDX, developers may need spend much time to read related papers. Also, it requires developers to follow Intel SGX SDK(Software Development Kit) to integrate their applications with Intel SGX, which will take lots efforts.

LibOS, which provides the capability to bring unmodified applications into Confidential Computing with Intel SGX and make it easy for developers to use SGX,  sometimes only provide simple samples or tutorials for developers to develop their applications, without providing more feasible, scalable functions or solutions.

Some CSPs now integrate Intel SGX technology in their cloud service, however, they provide limited resource or E2E reference solutions for their customers to demonstrate the usage of SGX in a practical way.

To well address above problems and provide more flexible solutions,  CCZoo contributes the **Confidential Computing Zoo Solution Table** as above for users, developers, Intel to

- Have an overall understanding of an End-to-End solution based on Intel® TEE and HE.
- Quick adoption or reference under similar scenarios in CCZoo based on Intel® TEE or HE.
- Propagate Intel security capabilities and deployments.
- Endorse by more customers, run in open model with broad partners.


---

# Confidential Computing Zoo Documentation

The official confidential computing zoo documentation can be found at https://cczoo.readthedocs.io.
Below are quick links to some of the most important papers:

- [TensorFlow Serving Cluster PPML based on SGX](https://cczoo.readthedocs.io/en/latest/Solutions/tensorflow-serving-cluster/index.html)
- [Horizontal Federal Learning based on SGX](https://cczoo.readthedocs.io/en/latest/Solutions/horizontal-federated-learning/hfl.html) 
---



# Community Involvement

- Please submit issues in this project if there is any question or request.
- Welcome PRs for contributions.
