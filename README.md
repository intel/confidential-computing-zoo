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

<table style="width:100%;" cellpadding="2" cellspacing="0" border="1" bordercolor="#000000">
	<tbody>
		<tr>
			<td rowspan="2" style="text-align:center;">
				<strong><span style="font-family:Arial;">Solutions</span></strong><br />
			</td>
			<td rowspan="2" style="text-align:center;">
				<span style="color:#333333;font-family:Arial;"><strong>Key   Applications</strong></span><br />
			</td>
			<td rowspan="2" style="text-align:center;">
				<span style="color:#333333;font-family:Arial;"><strong>Status</strong></span><br />
			</td>
			<td rowspan="2" style="text-align:center;">
				<span style="color:#333333;font-family:Arial;"><strong>Validated  in Public Cloud</strong></span><br />
			</td>
			<td colspan="7" style="text-align:center;">
				<strong><span style="font-family:Arial;">&nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp;&nbsp;&nbsp; &nbsp; S</span></strong><span style="color:#24292F;font-family:-apple-system, BlinkMacSystemFont, &quot;font-size:16px;background-color:#FFFFFF;"><strong><span style="font-family:Arial;">ecurity Technologies</span></strong><strong></strong></span><br />
			</td>
		</tr>
		<tr>
			<td style="text-align:center;">
				<span style="color:#333333;font-family:Arial;"><strong>TEE</strong></span><br />
			</td>
			<td style="text-align:center;">
				<strong><span style="font-family:Arial;">HE</span></strong> 
			</td>
			<td style="text-align:center;">
				<strong><span style="font-family:Arial;">LibOS</span></strong> 
			</td>
			<td style="text-align:center;">
				<p>
					<span style="font-family:Arial;"><strong>Remote</strong></span> 
				</p>
				<p>
					<span style="font-family:Arial;"><strong>Attestation</strong></span> 
				</p>
			</td>
			<td style="text-align:center;">
				<p>
					<span style="font-family:Arial;"><strong>Encryption</strong></span> 
				</p>
				<p>
					<span style="font-family:Arial;"><strong>/Decryption</strong></span> 
				</p>
			</td>
			<td style="text-align:center;">
				<strong></strong> 
				<p>
					<span style="color:#333333;font-family:Arial;"><strong>CPU HW&nbsp;</strong></span> 
				</p>
				<p>
					<span style="color:#333333;font-family:Arial;"><strong>Acceleration</strong></span> 
				</p>
			</td>
			<td style="text-align:center;">
				<strong><span style="font-family:Arial;">TLS</span></strong> 
			</td>
		</tr>
		<tr>
			<td>
				<span class="md-plain"><a href="https://cczoo.readthedocs.io/en/latest/Solutions/tensorflow-serving-cluster/index.html" target="_blank"><span style="font-family:Arial;"><strong>TensorFlow Serving Cluster PPML based on SGX</strong></span></a></span><br />
			</td>
			<td>
				<span style="color:#333333;font-family:Arial;">TensorFlow Serving, K8s</span><br />
			</td>
			<td>
				<strong><span style="font-family:Arial;">Published</span></strong> 
			</td>
			<td>
				<span class="md-plain"><a href="https://help.aliyun.com/document_detail/342755.html" target="_blank"><span style="font-family:Arial;"><strong>Aliyun ECS</strong></span></a></span><br />
			</td>
			<td>
				<span style="font-family:Arial;">SGX</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">Gramine</span> 
			</td>
			<td>
				<span style="font-family:Arial;">Yes</span> 
			</td>
			<td>
				<span style="font-family:Arial;">Yes</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">gRPC</span><br />
			</td>
		</tr>
		<tr>
			<td>
				<span class="md-plain"><a href="https://cczoo.readthedocs.io/en/latest/Solutions/horizontal-federated-learning/hfl.html" target="_blank"><span style="font-family:Arial;"><strong>Horizontal Federal Learning</strong></span></a></span><br />
			</td>
			<td>
				<span style="color:#333333;font-family:Arial;">TensorFlow</span><br />
			</td>
			<td>
				<strong><span style="font-family:Arial;">Published</span></strong><br />
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">SGX</span><br />
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">Gramine</span><br />
			</td>
			<td>
				<span style="color:#333333;font-family:Arial;">2-way RA-TLS</span><br />
			</td>
			<td>
				<span style="font-family:Arial;">Yes</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">gRPC</span><br />
			</td>
		</tr>
		<tr>
			<td>
				<span style="font-family:Arial;">Vertical Federal Learning based on SGX</span><br />
			</td>
			<td>
				<span style="color:#333333;font-family:Arial;">TensorFlow</span> 
			</td>
			<td>
				<span style="font-family:Arial;">In Progress</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">SGX</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">Gramine</span><br />
			</td>
			<td>
				<span style="color:#333333;font-family:Arial;">2-way RA-TLS</span><br />
			</td>
			<td>
				<span style="font-family:Arial;">Yes</span><br />
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">gRPC</span><br />
			</td>
		</tr>
		<tr>
			<td>
				<span style="color:#333333;font-family:Arial;">FATE Paillier logical regression+optimization</span><br />
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">In progress</span><br />
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="color:#333333;font-family:Arial;">Paillier</span><br />
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">Yes</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
		</tr>
		<tr>
			<td>
				<span style="color:#333333;font-family:Arial;">Leveled HE logical regression inference</span><br />
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">In progress</span><br />
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">HE</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">Yes</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
		</tr>
		<tr>
			<td>
				<span style="color:#333333;font-family:Arial;">MPC Optimization</span><br />
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">Not Start</span><br />
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">HE</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
		</tr>
		<tr>
			<td>
				<span style="color:#333333;font-family:Arial;">gRPC supporting Intel RA-TLS</span><br />
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="color:#333333;font-family:Arial;">In progress</span><br />
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="color:#333333;font-family:Arial;">SGX/TDX</span><br />
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="color:#333333;font-family:Arial;">2-way RA-TLS</span><br />
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">gRPC</span><br />
			</td>
		</tr>
		<tr>
			<td>
				<span style="color:#333333;font-family:Arial;">Attestation Server &amp; KMS</span><br />
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="color:#333333;font-family:Arial;">Not Start</span><br />
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="color:#333333;font-family:Arial;">SGX/TDX</span><br />
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">Yes</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
		</tr>
		<tr>
			<td>
				<span style="color:#333333;font-family:Arial;">Secure BigDL Recommend system</span><br />
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="color:#333333;font-family:Arial;">Not Start</span><br />
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">SGX</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">Yes</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
		</tr>
	</tbody>
</table>
<br />
<br />

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
