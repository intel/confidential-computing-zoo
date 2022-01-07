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


.. raw:: html

   <embed>
      <table style="width:100%;" cellpadding="2" cellspacing="0" border="1" bordercolor="#000000">
      	<tbody>
      		<tr>
      			<td rowspan="2" style="text-align:center;">
      				<strong><span style="font-family:Arial;">Sol<span style="background-color:#E53333;"></span>utions<span style="background-color:#E53333;"></span></span></strong><br />
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
      
   </embed>



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
