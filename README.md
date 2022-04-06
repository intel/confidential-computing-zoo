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

<table border="1" bordercolor="#000000" cellpadding="2" cellspacing="0" style="width:100%">
  <tbody>
    <tr>
      <td rowspan="3"><strong>&nbsp; Solution</strong>
      </td>
      <td colspan="11" rowspan="1"><strong>&nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; Security Components</strong>
      </td>
      <td colspan="1" rowspan="3">
        <p><strong><span style="color:#333333; font-family:Arial">Validated</span>
          <br />
          <span style="color:#333333; font-family:Arial">in Public Cloud</span></strong>
        </p>
      </td>
      <td colspan="1" rowspan="3">
        <p><strong>Status</strong>
        </p>
      </td>
    </tr>
    <tr>
      <td colspan="2" rowspan="1">
        <p><span style="color:#333333; font-family:Arial"><strong>&nbsp;&nbsp;TEE</strong></span>
        </p>
      </td>
      <td colspan="2" rowspan="1">
        <p><strong><span style="font-family:Arial">&nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp;LibOS</span></strong>
        </p>
      </td>
      <td colspan="2" rowspan="1">
        <p><strong>Remote Attestation</strong>
        </p>
      </td>
      <td colspan="2" rowspan="1">
        <p>&nbsp; &nbsp;&nbsp;<strong>KMS</strong>
        </p>
      </td>
      <td colspan="1" rowspan="2">
        <p><strong>HE</strong>
        </p>
      </td>
      <td colspan="1" rowspan="2" style="text-align:center;">
        <p style="text-align: left;"><font face="Arial"><strong>Crypto</strong></font>
        </p>
      </td>
      <td colspan="1" rowspan="2">
        <p><strong><span style="font-family:Arial">TLS</span></strong>
        </p>
      </td>
    </tr>
    <tr>
      <td colspan="1"><strong>SGX</strong>
      </td>
      <td colspan="1"><strong>TDX</strong>
      </td>
      <td dir="rtl" style="text-align:center;"><strong>Gramine</strong>
      </td>
      <td style="text-align:center;"><strong>Occlum</strong>
      </td>
      <td><strong><span style="font-size:22px">*</span><a href="https://cczoo.readthedocs.io/en/main/Solutions/rats-tls/index.html">RATS-TLS</a></strong>
      </td>
      <td><strong><span style="font-size:22px">*</span></strong><a href="https://cczoo.readthedocs.io/en/main/Solutions/grpc-ra-tls/index.html"><font face="Arial"><strong>RA-g</strong></font><strong><span style="font-family:Arial">RPC</span></strong></a>
      </td>
      <td style="text-align:center;"><strong>Vault</strong>
      </td>
      <td style="text-align:center;"><a href="https://cczoo.readthedocs.io/en/main/Solutions/ehsm-kms/index.html"><strong>eHSM-KMS</strong></a>
      </td>
    </tr>
    <tr>
      <td colspan="14"><span style="font-size:20px"><em><strong>Multi-Party Compute / Federated Learning</strong></em></span>
      </td>
    </tr>
    <tr>
      <td><span class="md-plain"><a href="https://cczoo.readthedocs.io/en/latest/Solutions/horizontal-federated-learning/hfl.html" target="_blank"><span style="font-family:Arial"><strong>Horizontal Federated Learning </strong></span></a>
        <br />
        (</span><span style="color:#333333; font-family:Arial">TensorFlow</span><span class="md-plain">)</span>
      </td>
      <td>Yes
      </td>
      <td>-
      </td>
      <td>Yes
      </td>
      <td>-
      </td>
      <td><font color="#333333" face="Arial">-</font>
      </td>
      <td><span style="color:#333333; font-family:Arial">Yes
        <br />
        (2-way)</span>
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td><span style="font-family:Arial">-</span>
      </td>
      <td><span style="font-family:Arial">Yes</span>
      </td>
      <td><span style="font-family:Arial">Yes
        <br />
        (RA-gRPC)</span>
      </td>
      <td>
        <p><span class="md-plain"><a href="https://cczoo.readthedocs.io/en/main/Solutions/horizontal-federated-learning/hfl.html#aliyun-ecs"><font face="Arial">Alibaba Cloud</font></a>,
          <br />
          <a href="https://cczoo.readthedocs.io/en/main/Solutions/horizontal-federated-learning/hfl.html#tencent-cloud">Tencent Cloud</a></span>
        </p>
      </td>
      <td><strong><span style="font-family:Arial">Published</span></strong>
      </td>
    </tr>
    <tr>
      <td><span style="font-family:Arial">Vertical Federated
        <br />
        Learning</span><span class="md-plain">&nbsp;
        <br />
        (</span><span style="color:#333333; font-family:Arial">TensorFlow</span><span class="md-plain">)</span>
      </td>
      <td><span style="font-family:Arial">Yes</span>
      </td>
      <td>-
      </td>
      <td>Yes
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td><span style="color:#333333; font-family:Arial">Yes
        <br />
        (2-way)</span>
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td><span style="font-family:Arial">Yes</span>
      </td>
      <td><span style="font-family:Arial">Yes
        <br />
        (RA-gRPC)</span>
      </td>
      <td>
        <p><span class="md-plain"><font face="Arial">Alibaba Cloud</font>,
          <br />
          Tencent Cloud</span>
        </p>
      </td>
      <td>Waiting For Publish
      </td>
    </tr>
    <tr>
      <td>Private Set
        <br />
        Intersection&nbsp;
      </td>
      <td><span style="font-family:Arial">Yes</span>
      </td>
      <td>-
      </td>
      <td>Yes
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>In Progress
      </td>
    </tr>
    <tr>
      <td><span style="color:#444444; font-family:Arial">Secure Logistic
        <br />
        Regression Training
        <br />
        Base on TEE &amp;&nbsp;</span><span style="color:#444444; font-family:Arial">HE&nbsp;</span>
      </td>
      <td><span style="font-family:Arial">Yes</span>
      </td>
      <td>-
      </td>
      <td>Yes
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>Yes
      </td>
      <td>Yes
      </td>
      <td>Yes
      </td>
      <td><span class="md-plain"><font face="Arial">Alibaba Cloud</font>,
        <br />
        Tencent Cloud</span>
      </td>
      <td>Waiting For Publish
      </td>
    </tr>
    <tr>
      <td colspan="14"><em><strong><span style="font-size:20px">Secure AI Inference &amp; Training</span></strong></em>
      </td>
    </tr>
    <tr>
      <td><span class="md-plain"><a href="https://cczoo.readthedocs.io/en/latest/Solutions/tensorflow-serving-cluster/index.html" target="_blank"><span style="font-family:Arial"><strong>TensorFlow Serving
        <br />
        Cluster PPML</strong></span></a>
        <br />
        (TensorFlow, K8S)</span>
      </td>
      <td>Yes
      </td>
      <td>-
      </td>
      <td>Yes
      </td>
      <td>Yes
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>Yes
      </td>
      <td>Yes
      </td>
      <td>
        <p><span class="md-plain"><a href="https://cczoo.readthedocs.io/en/main/Solutions/tensorflow-serving-cluster/index.html#alibaba-cloud"><font face="Arial">Alibaba Cloud</font></a>,
          <br />
          <a href="https://cczoo.readthedocs.io/en/main/Solutions/tensorflow-serving-cluster/index.html#tencent-cloud">Tencent Cloud</a></span>
        </p>
      </td>
      <td><span style="font-family:Arial">Published</span>
      </td>
    </tr>
    <tr>
      <td><span style="color:#333333; font-family:Arial">Leveled HE Logical Regression Inference</span>
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>Yes
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>In Progress
      </td>
    </tr>
    <tr>
      <td><span style="color:#333333; font-family:Arial">Secure BigDL
        <br />
        Recommend System</span>
      </td>
      <td>-
      </td>
      <td>Yes
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>Not Start
      </td>
    </tr>
    <tr>
      <td colspan="14"><span style="font-size:20px"><em><strong>Native Application Hosting</strong></em></span>
      </td>
    </tr>
    <tr>
      <td>Cross Language
        <br />
        framework Based
        <br />
        on Gramine
      </td>
      <td>Yes
      </td>
      <td>-
      </td>
      <td>Yes
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>In Progress
      </td>
    </tr>
    <tr>
      <td colspan="14"><em><strong><span style="font-size:20px">Attestation Server &amp; Key Management Service</span></strong></em>
      </td>
    </tr>
    <tr>
      <td>Attestation Server
      </td>
      <td>Yes
      </td>
      <td>Yes
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>Yes
      </td>
      <td>Yes
      </td>
      <td>Yes
      </td>
      <td>Yes
      </td>
      <td>-
      </td>
      <td>In Progress
      </td>
    </tr>
    <tr>
      <td><strong><a href="https://cczoo.readthedocs.io/en/main/Solutions/ehsm-kms/index.html">eHSM-KMS</a></strong>
      </td>
      <td>Yes
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>Yes
      </td>
      <td>-
      </td>
      <td>Yes
      </td>
      <td>Yes
      </td>
      <td>-
      </td>
      <td>Published
      </td>
    </tr>
    <tr>
      <td colspan="14"><strong><em><span style="font-size:20px">Optimization on Secure Libs</span></em></strong>
      </td>
    </tr>
    <tr>
      <td>Private Set
        <br />
        intersection
        <br />
        Optimization
        <br />
        on Xeon​
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>Yes
      </td>
      <td>Yes
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>Not Start
      </td>
    </tr>
    <tr>
      <td colspan="14"><span style="font-size:20px"><em><strong>Secure Database</strong></em></span>
      </td>
    </tr>
    <tr>
      <td>Secure Database
        <br />
        Querying Based
        <br />
        on HE
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>Yes
      </td>
      <td>Yes
      </td>
      <td>-
      </td>
      <td>-
      </td>
      <td>Not Start
      </td>
    </tr>
  </tbody>
</table>


---

# Incubating Component Projects

Besides solutions, CCZoo is also incubating component level projects with secure technologies, which can be standardized and versatile components, to be easily adopted in secure solutions. Incubating component  projects are now engaged in many solutions in CCZoo to validate  security and robustness.

<table border="1" bordercolor="#000000" cellpadding="2" cellspacing="0" style="width:100%">
  <tbody>
    <tr>
      <td colspan="1" rowspan="1"><strong>Incubating Component Project <span style="font-size:22px">&#39;*&#39;</span></strong>
      </td>
      <td colspan="1" rowspan="1"><span style="color:#333333; font-family:Arial"><strong>&nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; Description</strong></span>
      </td>
      <td rowspan="1"><strong>Status</strong>
      </td>
      <td colspan="1" rowspan="1"><span style="color:#333333; font-family:Arial"><strong>Validated in Public Cloud</strong></span>
      </td>
    </tr>
    <tr>
      <td colspan="1"><a href="https://cczoo.readthedocs.io/en/main/Solutions/rats-tls/index.html"><strong>RATS-TLS</strong></a>
      </td>
      <td>This project provides a proof-of-concept implementation on how to integrate Intel SGX remote attestation into the TLS connection setup. Conceptually, it extends the standard X.509 certificate&nbsp;with SGX-related information. It also provides three non-SGX clients (<a href="https://github.com/cloud-security-research/sgx-ra-tls/blob/master/deps/mbedtls/programs/ssl/ssl_client1.c">mbedtls</a>,&nbsp;<a href="https://github.com/cloud-security-research/sgx-ra-tls/blob/master/deps/wolfssl-examples/tls/client-tls.c">wolfSSL</a>,&nbsp;<a href="https://github.com/cloud-security-research/sgx-ra-tls/blob/master/openssl-client.c">OpenSSL</a>)&nbsp;to show how seamless remote attestation works with different TLS libraries.&nbsp;
      </td>
      <td>Published
      </td>
      <td><a href="https://cczoo.readthedocs.io/en/main/Cloud/cloudDeployment.html#azure-cloud"><font face="Arial">Azure Cloud</font></a>
      </td>
    </tr>
    <tr>
      <td colspan="1"><a href="https://cczoo.readthedocs.io/en/latest/Solutions/grpc-ra-tls/index.html"><strong>gRPC Supporting Intel RA-TLS</strong></a>
      </td>
      <td>This project provides an enhanced&nbsp;<a href="https://grpc.io/">gRPC</a>&nbsp;(Remote Procedure Call) framework to guarantee security during transmission and runtime via two-way&nbsp;<a href="https://arxiv.org/pdf/1801.05863">RA-TLS</a>&nbsp;(Intel SGX Remote Attestation with Transport Layer Security) based on&nbsp;<a href="https://en.wikipedia.org/wiki/Trusted_execution_environment">TEE</a>&nbsp;(Trusted Execution Environment).
      </td>
      <td>Published
      </td>
      <td><span class="md-plain"><font face="Arial"><a href="https://cczoo.readthedocs.io/en/main/Solutions/grpc-ra-tls/index.html#aliyun-ecs">Alibaba Cloud</a>,
        <br />
        <a href="https://cczoo.readthedocs.io/en/main/Solutions/grpc-ra-tls/index.html#tencent-cloud">Tencent Cloud</a></font></span>
      </td>
    </tr>
  </tbody>
</table>


---

# Cloud Deployment

Solutions and incubating component projects in CCZoo are constantly extended to be validated in public clouds to verify the versatility, stability, robustness. We will provide detialed configurations of each public clouds for reference, and notes of the diversity in each cloud for easy delopyment.

Below table shows solutions and component projects validated in public clouds. And it will be updated continuously.


<table border="1" cellpadding="1" cellspacing="1" style="width:500px">
  <tbody>
    <tr>
      <td colspan="2"><strong>&nbsp; &nbsp; &nbsp;Public Cloud</strong>
      </td>
      <td><strong>Alibaba Cloud</strong>
      </td>
      <td><strong>Tencent Cloud</strong>
      </td>
      <td><strong>Azure Cloud</strong>
      </td>
    </tr>
    <tr>
      <td rowspan="6" style="text-align: left;"><strong>Instance&nbsp;</strong>
      </td>
      <td style="text-align: left;">Type
      </td>
      <td><a href="https://help.aliyun.com/document_detail/108490.htm#section-bew-6jv-c0k">g7t</a>
      </td>
      <td><a href="https://cloud.tencent.com/document/product/213/11518#M6ce">M6ce.4XLARGE128&nbsp;</a>
      </td>
      <td><a href="https://docs.microsoft.com/en-us/azure/virtual-machines/dcv3-series">Standard_DC16s_v3</a>
      </td>
    </tr>
    <tr>
      <td style="text-align: left;">Kernel
      </td>
      <td>4.19.91-24
      </td>
      <td>5.4.119-19-0009.1
      </td>
      <td>5.13
      </td>
    </tr>
    <tr>
      <td style="text-align: left;">OS
      </td>
      <td>Alibaba Cloud Linux 2.1903
      </td>
      <td>TencentOS Server 3.1
      </td>
      <td>Ubuntu20.04
      </td>
    </tr>
    <tr>
      <td style="text-align: left;">Memory
      </td>
      <td>64G(32G EPC memory)
      </td>
      <td>64G(32G EPC Memory)
      </td>
      <td>128GB(64G EPC Memory)
      </td>
    </tr>
    <tr>
      <td style="text-align: left;">vCPU
      </td>
      <td>16
      </td>
      <td>16
      </td>
      <td>16
      </td>
    </tr>
    <tr>
      <td style="text-align: left;">PCCS Server
      </td>
      <td><a href="https://help.aliyun.com/document_detail/208095.html">sgx-dcap-server.cn-hangzhou.aliyuncs.com</a>
      </td>
      <td><a href="https://cloud.tencent.com/document/product/213/63353">sgx-dcap-server-tc.sh.tencent.cn&nbsp;</a>
      </td>
      <td><a href="https://docs.microsoft.com/en-us/azure/confidential-computing/quick-create-portal#install-azure-dcap-client">Azure DCAP</a>
      </td>
    </tr>
    <tr>
      <td colspan="2"><strong>Validated Solution&nbsp;</strong>
      </td>
      <td>
        <ul>
          <li><a href="https://cczoo.readthedocs.io/en/latest/Solutions/tensorflow-serving-cluster/index.html">TensorFlow Serving Cluster PPML&nbsp;</a></li>
          <li><a href="https://cczoo.readthedocs.io/en/latest/Solutions/horizontal-federated-learning/hfl.html">Horizontal Federated Learning&nbsp;</a></li>
          <li><a href="https://cczoo.readthedocs.io/en/latest/Solutions/grpc-ra-tls/index.html">gRPC supporting Intel RA-TLS</a></li>
          <li>Secure logistic regression training base on TEE &amp; HE</li>
        </ul>
      </td>
      <td>
        <ul>
          <li><a href="https://cczoo.readthedocs.io/en/latest/Solutions/tensorflow-serving-cluster/index.html">TensorFlow Serving Cluster PPML&nbsp;</a></li>
          <li><a href="https://cczoo.readthedocs.io/en/latest/Solutions/horizontal-federated-learning/hfl.html">Horizontal Federated Learning&nbsp;</a></li>
          <li><a href="https://cczoo.readthedocs.io/en/latest/Solutions/grpc-ra-tls/index.html">gRPC supporting Intel RA-TLS</a></li>
          <li>Secure logistic regression training base on TEE &amp; HE</li>
        </ul>
      </td>
      <td>
        <ul>
          <li><a href="https://cczoo.readthedocs.io/en/latest/Solutions/ehsm-kms/index.html">eHSM-KMS</a>
            <br />
            <br />
            <br />
            <br />
            &nbsp;</li>
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
