# Cloud Deployment

Solutions and incubating component projects in CCZoo are constantly extended to
be validated in public clouds to verify the versatility, stability, robustness.
We will provide detailed configurations of each public clouds for reference, and
notes of the diversity in each cloud for easy deployment.

We now have validated solutions in Alibaba Cloud, Tencent Cloud and Azure Cloud.
There will be more solutions be validated in more public cloud environments in the
future.

---

## Alibaba Cloud

[Aliyun ECS](https://help.aliyun.com/product/25365.html) (Elastic Compute Service)
is an IaaS (Infrastructure as a Service) level cloud computing service provided
by Alibaba Cloud. It builds security-enhanced instance families [g7t, c7t, r7t](https://help.aliyun.com/document_detail/207734.html)
based on Intel® SGX technology to provide a trusted and confidential environment
with a higher security level.

The configuration of the ECS instance as blow:

<table border="1" cellpadding="1" cellspacing="1" style="width:500px">
  <tbody>
    <tr>
      <td colspan="2"><strong>&nbsp; &nbsp; &nbsp; Public Cloud</strong>
      </td>
      <td><strong>Alibaba Cloud</strong>
      </td>
    </tr>
    <tr>
      <td rowspan="6" style="text-align: left;">
        <p>&nbsp;
        </p>
        <p><strong>Instance&nbsp;</strong>
        </p>
      </td>
      <td style="text-align: left;">Type
      </td>
      <td><a href="https://help.aliyun.com/document_detail/108490.htm#section-bew-6jv-c0k">g7t</a>
      </td>
    </tr>
    <tr>
      <td style="text-align: left;">Kernel
      </td>
      <td>4.19.91-24
      </td>
    </tr>
    <tr>
      <td style="text-align: left;">OS
      </td>
      <td>Alibaba Cloud Linux 2.1903
      </td>
    </tr>
    <tr>
      <td style="text-align: left;">Memory
      </td>
      <td>64G (32G EPC memory)
      </td>
    </tr>
    <tr>
      <td style="text-align: left;">vCPU
      </td>
      <td>16
      </td>
    </tr>
    <tr>
      <td style="text-align: left;">PCCS Server
      </td>
      <td><a href="https://help.aliyun.com/document_detail/208095.html">sgx-dcap-server.cn-hangzhou.aliyuncs.com</a>
      </td>
    </tr>
    <tr>
      <td colspan="2"><strong>&nbsp;
        <br />
        <br />
        <br />
        <br />
        Validated Solution</strong>
      </td>
      <td>
        <ul>
          <li><a href="https://cczoo.readthedocs.io/en/latest/Solutions/tensorflow-serving-cluster/index.html">TensorFlow Serving Cluster PPML&nbsp;</a>(<strong>*<a href="https://help.aliyun.com/document_detail/342755.html">Alibaba Best Practice</a>*</strong>)</li>
          <li><a href="https://cczoo.readthedocs.io/en/latest/Solutions/horizontal-federated-learning/hfl.html">Horizontal Federated Learning&nbsp;</a></li>
          <li><a href="https://cczoo.readthedocs.io/en/latest/Solutions/grpc-ra-tls/index.html">gRPC supporting Intel RA-TLS</a></li>
          <li>Secure logistic regression training base on TEE &amp; HE</li>
        </ul>
      </td>
    </tr>
  </tbody>
</table>


---

## Tencent Cloud

Tencent Cloud Virtual Machine (CVM) provide one instance named [M6ce](https://cloud.tencent.com/document/product/213/11518#M6ce),
which supports Intel® SGX encrypted computing technology.

The configuration of the M6ce instance as blow:

<table border="1" cellpadding="1" cellspacing="1" style="width:500px">
  <tbody>
    <tr>
      <td colspan="2"><strong>&nbsp; &nbsp; Public Cloud</strong>
      </td>
      <td><strong>Tencent Cloud</strong>
      </td>
    </tr>
    <tr>
      <td rowspan="6" style="text-align: left;">
        <p>&nbsp;
        </p>
        <p><strong>Instance&nbsp;</strong>
        </p>
      </td>
      <td style="text-align: left;">Type
      </td>
      <td><a href="https://cloud.tencent.com/document/product/213/11518#M6ce">M6ce.4XLARGE128&nbsp;</a>
      </td>
    </tr>
    <tr>
      <td style="text-align: left;">Kernel
      </td>
      <td>5.4.119-19-0009.1
      </td>
    </tr>
    <tr>
      <td style="text-align: left;">OS
      </td>
      <td>TencentOS Server 3.1
      </td>
    </tr>
    <tr>
      <td style="text-align: left;">Memory
      </td>
      <td>64G(32G EPC Memory)
      </td>
    </tr>
    <tr>
      <td style="text-align: left;">vCPU
      </td>
      <td>16
      </td>
    </tr>
    <tr>
      <td style="text-align: left;">PCCS Server
      </td>
      <td><a href="https://cloud.tencent.com/document/product/213/63353">sgx-dcap-server-tc.sh.tencent.cn&nbsp;</a>
      </td>
    </tr>
    <tr>
      <td colspan="2">
        <br />
        <br />
        <br />
        <strong>Validated Solution&nbsp;</strong>
      </td>
      <td>
        <ul>
          <li><a href="https://cczoo.readthedocs.io/en/latest/Solutions/tensorflow-serving-cluster/index.html">TensorFlow Serving Cluster PPML&nbsp;</a></li>
          <li><a href="https://cczoo.readthedocs.io/en/latest/Solutions/horizontal-federated-learning/hfl.html">Horizontal Federated Learning&nbsp;</a></li>
          <li><a href="https://cczoo.readthedocs.io/en/latest/Solutions/grpc-ra-tls/index.html">gRPC supporting Intel RA-TLS</a></li>
          <li>Secure logistic regression training base on TEE &amp; HE</li>
        </ul>
      </td>
    </tr>
  </tbody>
</table>


---

## Azure Cloud

[Azure confidential computing services](https://azure.microsoft.com/en-us/solutions/confidential-compute/) are
available and provide access to VMs with Intel SGX enabled in [DCsv2](https://docs.microsoft.com/en-us/azure/virtual-machines/dcv2-series) and [DCsv3](https://docs.microsoft.com/en-us/azure/virtual-machines/dcv3-series)
VM instances. 

The configuration of the DCsv3 instance as blow:

<table border="1" cellpadding="1" cellspacing="1" style="width:500px">
  <tbody>
    <tr>
      <td colspan="2"><strong>&nbsp; &nbsp; &nbsp; &nbsp; &nbsp;Public Cloud</strong>
      </td>
      <td><strong>&nbsp; &nbsp; Azure Cloud</strong>
      </td>
    </tr>
    <tr>
      <td rowspan="6">
        <p>&nbsp;
        </p>
        <p><strong>Instance&nbsp;</strong>
        </p>
      </td>
      <td style="text-align: left;">Type
      </td>
      <td><a href="https://docs.microsoft.com/en-us/azure/virtual-machines/dcv3-series">Standard_DC16s_v3</a>
      </td>
    </tr>
    <tr>
      <td style="text-align: left;">Kernel
      </td>
      <td>5.13
      </td>
    </tr>
    <tr>
      <td style="text-align: left;">OS
      </td>
      <td>Ubuntu20.04
      </td>
    </tr>
    <tr>
      <td style="text-align: left;">Memory
      </td>
      <td>128GB(64G EPC Memory)
      </td>
    </tr>
    <tr>
      <td style="text-align: left;">vCPU
      </td>
      <td>16
      </td>
    </tr>
    <tr>
      <td style="text-align: left;">PCCS Server
      </td>
      <td><a href="https://docs.microsoft.com/en-us/azure/confidential-computing/quick-create-portal#install-azure-dcap-client">Azure DCAP</a>
      </td>
    </tr>
    <tr>
      <td colspan="2">
        <p>
          <br />
          <br />
          <strong>Validated Solution&nbsp;</strong>
        </p>
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
