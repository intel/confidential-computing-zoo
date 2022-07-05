<div align="center">

<p align="center"> <img src="documents/readthedoc/docs/source/Images/cczoo.jpg" height="140px"><br></p>

</div>

Confidential Computing Zoo (CCZoo) is a collection of code-ready reference solutions, which can be used as a copy-paste developer guide, demonstrating how to apply modern security technologies to real-life cloud business scenarios, in order to facilitate the developers to build their own end-to-end Confidential Computing solutions more easily. Some of the solutions are also validated on the public cloud services, such as Alibaba Cloud, Tencent Cloud, AWS, Azure, etc. Please see [Cloud Deployment](https://github.com/intel/confidential-computing-zoo#cloud-deployment).

The concerned modern security technologies are (but not limited to): TEE (Trusted Execution Environment, such as Intel® SGX and TDX), HE (Homomorphic Encryption) and its
hardware accelerations, Remote Attestation, LibOS, cryptographic and its hardware accelerations. The concerned business scenarios are (but not limited to): cloud native AI
inference, vertical and horizontal federated learning, big data analytics, key management, RPC (Remote Process Call, such as gRPC), etc.

CCZoo maintains a live table, as below, to indicate the correlations between business usages (rows) and security technologies (columns). Each hyperlink will direct you to the
document section that explains the corresponding details and then guides you to the source codes. Enjoy!

#  Solution List (Solution to Component Correlation)

<table border="1" bordercolor="#000000" cellpadding="2" cellspacing="0" style="width:100%;">
	<tbody>
		<tr>
			<td rowspan="3">
				<strong>&nbsp; Solution</strong> 
			</td>
			<td colspan="11" rowspan="1">
				<strong>&nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; Security Components</strong> 
			</td>
			<td colspan="1" rowspan="3">
				<p>
					<strong><span style="color:#333333;font-family:Arial;">Validated</span> <br />
<span style="color:#333333;font-family:Arial;">in Public Cloud</span></strong> 
				</p>
			</td>
			<td colspan="1" rowspan="3">
				<p>
					<strong>Status</strong> 
				</p>
			</td>
		</tr>
		<tr>
			<td colspan="2" rowspan="1">
				<p>
					<span style="color:#333333;font-family:Arial;"><strong>&nbsp;&nbsp;TEE</strong></span> 
				</p>
			</td>
			<td colspan="2" rowspan="1">
				<p>
					<strong><span style="font-family:Arial;">&nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp;LibOS</span></strong> 
				</p>
			</td>
			<td colspan="2" rowspan="1">
				<p>
					<strong>Remote Attestation</strong> 
				</p>
			</td>
			<td colspan="2" rowspan="1">
				<p>
					&nbsp; &nbsp;&nbsp;<strong>KMS</strong> 
				</p>
			</td>
			<td colspan="1" rowspan="2">
				<p>
					<strong>HE</strong> 
				</p>
			</td>
			<td colspan="1" rowspan="2" style="text-align:center;">
				<p style="text-align:left;">
					<span><strong>Crypto</strong></span> 
				</p>
			</td>
			<td colspan="1" rowspan="2">
				<p>
					<strong><span style="font-family:Arial;">TLS</span></strong> 
				</p>
			</td>
		</tr>
		<tr>
			<td colspan="1">
				<strong>SGX</strong> 
			</td>
			<td colspan="1">
				<strong>TDX</strong> 
			</td>
			<td style="text-align:center;">
				<strong>Gramine</strong> 
			</td>
			<td style="text-align:center;">
				<strong>Occlum</strong> 
			</td>
			<td>
				<strong><span style="font-size:22px;">*</span><a href="https://cczoo.readthedocs.io/en/main/Solutions/rats-tls/index.html">RATS-TLS</a></strong> 
			</td>
			<td>
				<strong><span style="font-size:22px;">*</span></strong><a href="https://cczoo.readthedocs.io/en/main/Solutions/grpc-ra-tls/index.html"><span><strong>RA-TLS g</strong></span><strong><span style="font-family:Arial;">RPC</span></strong></a> 
			</td>
			<td style="text-align:center;">
				<strong>Vault</strong> 
			</td>
			<td style="text-align:center;">
				<a href="https://cczoo.readthedocs.io/en/main/Solutions/ehsm-kms/index.html"><strong>eHSM-KMS</strong></a> 
			</td>
		</tr>
		<tr>
			<td colspan="14">
				<span style="font-size:20px;"><em><strong>Multi-Party Compute / Federated Learning</strong></em></span> 
			</td>
		</tr>
		<tr>
			<td>
				<span class="md-plain"><a href="https://cczoo.readthedocs.io/en/latest/Solutions/horizontal-federated-learning/hfl.html" target="_blank"><span style="font-family:Arial;"><strong>Horizontal Federated Learning </strong></span></a> <br />
(</span><span style="color:#333333;font-family:Arial;">TensorFlow</span><span class="md-plain">)</span> 
			</td>
			<td>
				Yes
			</td>
			<td>
				-
			</td>
			<td>
				Yes
			</td>
			<td>
				-
			</td>
			<td>
				<span>-</span> 
			</td>
			<td>
				<span style="color:#333333;font-family:Arial;">Yes <br />
(2-way)</span> 
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				<span style="font-family:Arial;">-</span> 
			</td>
			<td>
				<span style="font-family:Arial;">Yes</span> 
			</td>
			<td>
				<span style="font-family:Arial;">Yes <br />
(RA-gRPC)</span> 
			</td>
			<td>
				<p>
					<span class="md-plain"><a href="https://cczoo.readthedocs.io/en/main/Solutions/horizontal-federated-learning/hfl.html#aliyun-ecs"><span>Alibaba Cloud</span></a>, <br />
<a href="https://cczoo.readthedocs.io/en/main/Solutions/horizontal-federated-learning/hfl.html#tencent-cloud">Tencent Cloud</a>,<br />
<a href="https://cczoo.readthedocs.io/en/main/Solutions/horizontal-federated-learning/hfl.html" target="_blank"><span>ByteDance Cloud</span><br />
</a></span><a href="https://cczoo.readthedocs.io/en/main/Solutions/horizontal-federated-learning/hfl.html" target="_blank"> </a>
				</p>
			</td>
			<td>
				<strong><span style="font-family:Arial;">Published</span></strong> 
			</td>
		</tr>
		<tr>
			<td>
				<span style="font-family:Arial;"><a href="https://cczoo.readthedocs.io/en/latest/Solutions/vertical-federated-learning/vfl.html" target="_blank"><strong>Vertical Federated </strong><br />
<strong> Learning</strong></a></span><span class="md-plain"><a href="https://cczoo.readthedocs.io/en/latest/Solutions/vertical-federated-learning/vfl.html" target="_blank">&nbsp;</a> <br />
(</span><span style="color:#333333;font-family:Arial;">TensorFlow</span><span class="md-plain">)</span> 
			</td>
			<td>
				<span style="font-family:Arial;">Yes</span> 
			</td>
			<td>
				-
			</td>
			<td>
				Yes
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				<span style="color:#333333;font-family:Arial;">Yes <br />
(2-way)</span> 
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				<span style="font-family:Arial;">Yes</span> 
			</td>
			<td>
				<span style="font-family:Arial;">Yes <br />
(RA-gRPC)</span> 
			</td>
			<td>
				<p>
					<span class="md-plain"><span><a href="https://cczoo.readthedocs.io/en/latest/Solutions/vertical-federated-learning/vfl.html" target="_blank">Alibaba Cloud</a></span>, <br />
<a href="https://cczoo.readthedocs.io/en/latest/Solutions/vertical-federated-learning/vfl.html" target="_blank">Tencent Cloud</a>,<br />
<a href="https://cczoo.readthedocs.io/en/latest/Solutions/vertical-federated-learning/vfl.html" target="_blank">ByteDance Cloud</a></span> 
				</p>
			</td>
			<td>
				<strong><span style="font-family:Arial;">Published</span></strong> 
			</td>
		</tr>
		<tr>
			<td>
				Private Set <br />
Intersection&nbsp;
			</td>
			<td>
				<span style="font-family:Arial;">Yes</span> 
			</td>
			<td>
				-
			</td>
			<td>
				Yes
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				In Progress
			</td>
		</tr>
		<tr>
			<td>
				<span style="color:#444444;font-family:Arial;">Secure Logistic <br />
Regression Training <br />
Base on TEE &amp;&nbsp;</span><span style="color:#444444;font-family:Arial;">HE&nbsp;</span> 
			</td>
			<td>
				<span style="font-family:Arial;">Yes</span> 
			</td>
			<td>
				-
			</td>
			<td>
				Yes
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				Yes
			</td>
			<td>
				Yes
			</td>
			<td>
				Yes
			</td>
			<td>
				<span class="md-plain"><span>Alibaba Cloud</span>, <br />
Tencent Cloud</span> 
			</td>
			<td>
				Waiting For Publish
			</td>
		</tr>
		<tr>
			<td colspan="14">
				<em><strong><span style="font-size:20px;">Secure AI Inference &amp; Training</span></strong></em> 
			</td>
		</tr>
		<tr>
			<td>
				<span class="md-plain"><a href="https://cczoo.readthedocs.io/en/latest/Solutions/tensorflow-serving-cluster/index.html" target="_blank"><span style="font-family:Arial;"><strong>TensorFlow Serving <br />
Cluster PPML</strong></span></a> <br />
(TensorFlow, K8S)</span> 
			</td>
			<td>
				Yes
			</td>
			<td>
				-
			</td>
			<td>
				Yes
			</td>
			<td>
				Yes
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				Yes
			</td>
			<td>
				Yes
			</td>
			<td>
				<p>
					<span class="md-plain"><a href="https://cczoo.readthedocs.io/en/main/Solutions/tensorflow-serving-cluster/index.html#alibaba-cloud"><span>Alibaba Cloud</span></a>, <br />
<a href="https://cczoo.readthedocs.io/en/main/Solutions/tensorflow-serving-cluster/index.html#tencent-cloud">Tencent Cloud</a>,<br />
<a href="https://cczoo.readthedocs.io/en/main/Solutions/tensorflow-serving-cluster/index.html#bytedance-cloud" target="_blank"><span>ByteDance Cloud</span><br />
</a></span><a href="https://cczoo.readthedocs.io/en/main/Solutions/tensorflow-serving-cluster/index.html#bytedance-cloud" target="_blank"> </a>
				</p>
			</td>
			<td>
				<span style="font-family:Arial;">Published</span> 
			</td>
		</tr>
		<tr>
			<td>
				<span style="color:#333333;font-family:Arial;">Leveled HE Logical Regression Inference</span> 
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				Yes
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				In Progress
			</td>
		</tr>
		<tr>
			<td>
				<span class="md-plain"><a href="https://bigdl.readthedocs.io/en/latest/doc/PPML/Overview/ppml.html" target="_blank"><span style="font-family:Arial;"><strong>BigDL PPML</strong></span> 
			</td>
			<td>
				Yes
			</td>
			<td>
				Yes
			</td>
			<td>
				Yes
			</td>
			<td>
				Yes
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				Yes
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				<p>
					<span class="md-plain"><a href="https://www.intel.com/content/dam/www/central-libraries/us/en/documents/alibaba-ppml-ai-blog-pdf.pdf"><span>Ant Group</span></a>, <br />
<a href="https://networkbuilders.intel.com/solutionslibrary/reference-architecture-for-confidential-computing-on-skt-5g-mec">SKT</a>
				</p>
			</td>
			<td>
				In Progress
			</td>
		</tr>
		<tr>
			<td colspan="14">
				<span style="font-size:20px;"><em><strong>Native Application Hosting</strong></em></span> 
			</td>
		</tr>
		<tr>
			<td>
				<a href="https://cczoo.readthedocs.io/en/latest/Solutions/cross_language_framework_based_gramine/Readme.html" target="_blank"><strong>Cross Language </strong><br />
<strong> framework Based </strong><br />
<strong> on Gramine</strong></a>
			</td>
			<td>
				Yes
			</td>
			<td>
				-
			</td>
			<td>
				Yes
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				Tencent Cloud
			</td>
			<td>
				<strong><span style="font-family:Arial;">Published</span></strong> 
			</td>
		</tr>
		<tr>
			<td colspan="14">
				<em><strong><span style="font-size:20px;">Attestation Server &amp; Key Management Service</span></strong></em> 
			</td>
		</tr>
		<tr>
			<td>
				<strong><a href="https://cczoo.readthedocs.io/en/latest/Solutions/attestation-secret-provision/index.html" target="_blank">Attestation and Secret Provision Service</a></strong>
			</td>
			<td>
				Yes
			</td>
			<td>
				Yes
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				Yes
			</td>
			<td>
				Yes
			</td>
			<td>
				-
			</td>
			<td>
				Yes
			</td>
			<td>
				-
			</td>
			<td>
				Yes
			</td>
			<td>
				Yes
			</td>
			<td>
				-
			</td>
			<td>
				<strong><span style="font-family:Arial;">Published</span></strong> 
			</td>
		</tr>
		<tr>
			<td>
				<strong><a href="https://cczoo.readthedocs.io/en/main/Solutions/ehsm-kms/index.html">eHSM-KMS</a></strong> 
			</td>
			<td>
				Yes
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				Yes
			</td>
			<td>
				-
			</td>
			<td>
				Yes
			</td>
			<td>
				Yes
			</td>
			<td>
				-
			</td>
			<td>
				<strong><span style="font-family:Arial;">Published</span></strong> 
			</td>
		</tr>
		<tr>
			<td colspan="14">
				<strong><em><span style="font-size:20px;">Optimization on Secure Libs</span></em></strong> 
			</td>
		</tr>
		<tr>
			<td>
				Private Set <br />
intersection <br />
Optimization <br />
on Xeon
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				Yes
			</td>
			<td>
				Yes
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				Not Start
			</td>
		</tr>
		<tr>
			<td colspan="14">
				<span style="font-size:20px;"><em><strong>Secure Database</strong></em></span> 
			</td>
		</tr>
		<tr>
			<td>
				Secure Database <br />
Querying Based <br />
on HE
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				Yes
			</td>
			<td>
				Yes
			</td>
			<td>
				-
			</td>
			<td>
				-
			</td>
			<td>
				Not Start
			</td>
		</tr>
	</tbody>
</table>

---

# Incubating Component Projects

Besides reference solutions, CCZoo is also incubating new projects of key security
components that are commonly used by multiple CCZoo reference solutions. Once any
of them is proven useful enough and stable enough via a thorough validation with
CCZoo reference solutions running on various public cloud services, it will graduate
from CCZoo and evolve to a standalone project.

<table border="1" bordercolor="#000000" cellpadding="2" cellspacing="0" style="width:100%;">
	<tbody>
		<tr>
			<td colspan="1" rowspan="1">
				<strong>Incubating Component Project <span style="font-size:22px;">'*'</span></strong> 
			</td>
			<td colspan="1" rowspan="1">
				<span style="color:#333333;font-family:Arial;"><strong>&nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; Description</strong></span> 
			</td>
			<td rowspan="1">
				<strong>Status</strong> 
			</td>
			<td colspan="1" rowspan="1">
				<span style="color:#333333;font-family:Arial;"><strong>Validated in Public Cloud</strong></span> 
			</td>
		</tr>
		<tr>
			<td colspan="1">
				<a href="https://cczoo.readthedocs.io/en/main/Solutions/rats-tls/index.html"><strong>RATS-TLS</strong></a> 
			</td>
			<td>
				This project provides a proof-of-concept implementation on how to integrate Intel SGX and TDX remote attestation into the TLS connection setup. Conceptually, it extends the standard X.509 certificate&nbsp;with SGX and TDX related information. It also provides two non-SGX clients (Wolfssl and OpenSSL)&nbsp;to show how seamless remote attestation works with different TLS libraries.&nbsp;
			</td>
			<td>
				Published
			</td>
			<td>
				<span class="md-plain"><span><a href="https://cczoo.readthedocs.io/en/main/Solutions/grpc-ra-tls/index.html#aliyun-ecs">Alibaba Cloud</a></span></span> 
			</td>
		</tr>
		<tr>
			<td colspan="1">
				<a href="https://cczoo.readthedocs.io/en/latest/Solutions/grpc-ra-tls/index.html"><strong>RA-TLS Enhanced gRPC</strong></a> 
			</td>
			<td>
				This project provides an enhanced&nbsp;<a href="https://grpc.io/">gRPC</a>&nbsp;(Remote Procedure Call) framework to guarantee security during transmission and runtime via two-way&nbsp;<a href="https://arxiv.org/pdf/1801.05863">RA-TLS</a>&nbsp;(Intel SGX Remote Attestation with Transport Layer Security) based on&nbsp;<a href="https://en.wikipedia.org/wiki/Trusted_execution_environment">TEE</a>&nbsp;(Trusted Execution Environment).
			</td>
			<td>
				Published
			</td>
			<td>
				<span class="md-plain"><span><a href="https://cczoo.readthedocs.io/en/main/Solutions/grpc-ra-tls/index.html#aliyun-ecs">Alibaba Cloud</a>, <br />
<a href="https://cczoo.readthedocs.io/en/main/Solutions/grpc-ra-tls/index.html#tencent-cloud">Tencent Cloud</a>,<br />
<a href="https://cczoo.readthedocs.io/en/main/Solutions/grpc-ra-tls/index.html#bytedance-cloud" target="_blank">ByteDance Cloud</a></span></span> 
			</td>
		</tr>
	</tbody>
</table>


---

# Cloud Deployment

Solutions and incubating component projects in CCZoo are constantly extended to be validated in public clouds to verify the versatility, stability, robustness. We will provide detialed configurations of each public clouds for reference, and notes of the diversity in each cloud for easy delopyment.

Below table shows solutions and component projects validated in public clouds. And it will be updated continuously.


<table border="1" cellpadding="1" cellspacing="1" style="width:500px;">
	<tbody>
		<tr>
			<td colspan="2">
				<strong>&nbsp; &nbsp; &nbsp;Public Cloud</strong> 
			</td>
			<td>
				<strong>Alibaba Cloud</strong> 
			</td>
			<td>
				<strong>ByteDance</strong> <strong>Cloud</strong> 
			</td>
			<td>
				<strong>Tencent Cloud</strong> 
			</td>
		</tr>
		<tr>
			<td style="text-align:left;" rowspan="6">
				<strong>Instance&nbsp;</strong> 
			</td>
			<td style="text-align:left;">
				Type
			</td>
			<td>
				<a href="https://help.aliyun.com/document_detail/108490.htm#section-bew-6jv-c0k">g7t</a><br />
			</td>
			<td>
				<div>
					ecs.ebmg2t.32xlarge
				</div>
			</td>
			<td>
				<a href="https://cloud.tencent.com/document/product/213/11518#M6ce">M6ce.4XLARGE128&nbsp;</a> 
			</td>
		</tr>
		<tr>
			<td style="text-align:left;">
				Kernel
			</td>
			<td>
				4.19.91-24
			</td>
			<td>
				<div>
					kernel-5.15
				</div>
			</td>
			<td>
				<span>5.4.119-19-0009.1</span><br />
			</td>
		</tr>
		<tr>
			<td style="text-align:left;">
				OS
			</td>
			<td>
				Alibaba Cloud Linux 2.1903
			</td>
			<td>
				<span id="__kindeditor_bookmark_start_109__"></span>Ubuntu20.04
			</td>
			<td>
				<span>TencentOS Server 3.1</span><br />
			</td>
		</tr>
		<tr>
			<td style="text-align:left;">
				Memory
			</td>
			<td>
				64G(32G EPC memory)
			</td>
			<td>
				<div>
					512GB(<span>25</span><span>6GB&nbsp;</span>EPC memory)
				</div>
			</td>
			<td>
				<span>64G(32G EPC <span>memory</span>)</span><br />
			</td>
		</tr>
		<tr>
			<td style="text-align:left;">
				vCPU
			</td>
			<td>
				16
			</td>
			<td>
				16
			</td>
			<td>
				16<br />
			</td>
		</tr>
		<tr>
			<td style="text-align:left;">
				PCCS Server
			</td>
			<td>
				<a href="https://help.aliyun.com/document_detail/208095.html">sgx-dcap-server.cn-hangzhou.aliyuncs.com</a> 
			</td>
			<td>
				<div>
					<a target="_blank" class="link rich-text-anchor __anchor-intercept-flag__" href="https://sgx-dcap-server.bytedance.com">sgx-dcap-server.bytedance.com</a> 
				</div>
			</td>
			<td>
				<a href="https://cloud.tencent.com/document/product/213/63353">sgx-dcap-server-tc.sh.tencent.cn&nbsp;</a><br />
			</td>
		</tr>
		<tr>
			<td colspan="2">
				<strong>Validated Solution&nbsp;</strong><br />
			</td>
			<td>
				<ul>
					<li>
						<a href="https://cczoo.readthedocs.io/en/latest/Solutions/tensorflow-serving-cluster/index.html">TensorFlow Serving Cluster PPML</a> 
					</li>
				</ul>
				<ul>
					<li>
						<a href="https://cczoo.readthedocs.io/en/latest/Solutions/horizontal-federated-learning/hfl.html">Horizontal Federated Learning</a> 
					</li>
				</ul>
				<ul>
					<li>
						<a href="https://cczoo.readthedocs.io/en/latest/Solutions/grpc-ra-tls/index.html">RA-TLS Enhanced gRPC</a> 
					</li>
					<li>
						Secure logistic regression training base on TEE &amp; HE
					</li>
				</ul>
			</td>
			<td>
				<ul>
					<li>
						<a href="https://cczoo.readthedocs.io/en/latest/Solutions/tensorflow-serving-cluster/index.html">TensorFlow Serving Cluster PPML</a> 
					</li>
				</ul>
				<ul>
					<li>
						<a href="https://cczoo.readthedocs.io/en/latest/Solutions/horizontal-federated-learning/hfl.html">Horizontal Federated Learning</a> 
					</li>
				</ul>
				<ul>
					<li>
						<a href="https://cczoo.readthedocs.io/en/latest/Solutions/grpc-ra-tls/index.html">RA-TLS Enhanced gRPC</a> 
					</li>
					<li>
						<a href="https://cczoo.readthedocs.io/en/latest/Solutions/vertical-federated-learning/vfl.html" target="_blank">Vertical Federated Learning</a> 
					</li>
				</ul>
			</td>
			<td>
				<ul>
					<li>
						<a href="https://cczoo.readthedocs.io/en/latest/Solutions/tensorflow-serving-cluster/index.html">TensorFlow Serving Cluster PPML</a> 
					</li>
				</ul>
				<ul>
					<li>
						<a href="https://cczoo.readthedocs.io/en/latest/Solutions/horizontal-federated-learning/hfl.html">Horizontal Federated Learning</a> 
					</li>
				</ul>
				<ul>
					<li>
						<a href="https://cczoo.readthedocs.io/en/latest/Solutions/grpc-ra-tls/index.html">RA-TLS Enhanced gRPC</a> 
					</li>
					<li>
						Secure logistic regression training base on TEE &amp; HE
					</li>
				</ul>
			</td>
		</tr>
	</tbody>
</table>


---

# Confidential Computing Zoo Documentation

The official confidential computing zoo documentation can be found at https://cczoo.readthedocs.io.

---

# Community Involvement

- Please submit issues in this project if there is any question or request.
- Welcome PRs for contributions.

Welcome to join the Wechat group or Slack channel for CCZoo tech discussion.
- [Wechat](https://github.com/intel/confidential-computing-zoo/issues/18)
- [Slack Channel](https://join.slack.com/t/cc-zoo/shared_invite/zt-13c1of71t-1U8C61vbLZWxu0JuwbGi5w)


You can check CCZoo previous PDT meeting munites [here](https://github.com/intel/confidential-computing-zoo/wiki/CCZoo-PDT-Meeting).
