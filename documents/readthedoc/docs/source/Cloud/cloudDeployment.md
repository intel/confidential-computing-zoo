# Cloud Deployment

Solutions and incubating component projects in CCZoo are constantly extended to
be validated in public clouds to verify the versatility, stability, robustness.
We will provide detailed configurations of each public cloud for reference, and
notes of the diversity in each cloud for easy deployment.

We now have validated solutions in Alibaba Cloud, Tencent Cloud, ByteDance Cloud, and Microsoft Azure.
Additional solutions will be validated in more public cloud environments.

---

## Alibaba Cloud

[Aliyun ECS](https://help.aliyun.com/product/25365.html) (Elastic Compute Service)
is an IaaS (Infrastructure as a Service) level cloud computing service provided
by Alibaba Cloud. It builds security-enhanced instance families [g7t, c7t, r7t](https://help.aliyun.com/document_detail/207734.html)
based on Intel® SGX technology to provide a trusted and confidential environment
with a higher security level.

The configuration of the ECS instance as below:

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
        Validated Solutions</strong>
      </td>
      <td>
        <ul>
          <li><a href="https://cczoo.readthedocs.io/en/latest/Solutions/tensorflow-serving-cluster/index.html">TensorFlow Serving Cluster PPML&nbsp;</a>(<strong>*<a href="https://help.aliyun.com/document_detail/342755.html">Alibaba Best Practice</a>*</strong>)</li>
          <li><a href="https://cczoo.readthedocs.io/en/latest/Solutions/horizontal-federated-learning/hfl.html">Horizontal Federated Learning&nbsp;</a></li>
          <li><a href="https://cczoo.readthedocs.io/en/latest/Solutions/grpc-ra-tls/index.html">RA-TLS Enhanced gRPC</a></li>
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

The configuration of the M6ce instance as below:

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
        <strong>Validated Solutions&nbsp;</strong>
      </td>
      <td>
        <ul>
          <li><a href="https://cczoo.readthedocs.io/en/latest/Solutions/tensorflow-serving-cluster/index.html">TensorFlow Serving Cluster PPML&nbsp;</a></li>
          <li><a href="https://cczoo.readthedocs.io/en/latest/Solutions/horizontal-federated-learning/hfl.html">Horizontal Federated Learning&nbsp;</a></li>
          <li><a href="https://cczoo.readthedocs.io/en/latest/Solutions/grpc-ra-tls/index.html">RA-TLS Enhanced gRPC</a></li>
          <li>Secure logistic regression training base on TEE &amp; HE</li>
        </ul>
      </td>
    </tr>
  </tbody>
</table>


---

## ByteDance Cloud

ByteDance Cloud (Volcengine SGX Instances) provides the instance named `ebmg2t`,
which supports Intel® SGX encrypted computing technology. Now ByteDance Cloud only
provides SGX instance based on bare metal for customers in whitelist.

The configuration of the M6ce instance as below:

<table border="1" cellpadding="1" cellspacing="1" style="width:500px;">
	<tbody>
		<tr>
			<td colspan="2">
				<strong>&nbsp; &nbsp; Public Cloud</strong> 
			</td>
			<td>
				<strong>ByteDance Cloud</strong> 
			</td>
		</tr>
		<tr>
			<td rowspan="6" style="text-align:left;">
				<p>
					<span>&nbsp;</span> 
				</p>
				<p>
					<strong>Instance&nbsp;</strong> 
				</p>
			</td>
			<td style="text-align:left;">
				<span>Type</span> 
			</td>
			<td>
				<div>
					<span>ebmg2t.32xlarge (Bare Metal)</span> 
				</div>
			</td>
		</tr>
		<tr>
			<td style="text-align:left;">
				<span>Kernel</span> 
			</td>
			<td>
				<div>
					<span>kernel-5.15</span> 
				</div>
			</td>
		</tr>
		<tr>
			<td style="text-align:left;">
				<span>OS</span> 
			</td>
			<td>
				<span>Ubuntu20.04</span> 
			</td>
		</tr>
		<tr>
			<td style="text-align:left;">
				<span>Memory</span> 
			</td>
			<td>
				<span>512G(256G EPC Memory)</span> 
			</td>
		</tr>
		<tr>
			<td style="text-align:left;">
				<span>vCPU</span> 
			</td>
			<td>
				<span>16</span> 
			</td>
		</tr>
		<tr>
			<td style="text-align:left;">
				<span>PCCS Server</span> 
			</td>
			<td>
				<span><span>sgx-dcap-server.bytedance.com </span></span> 
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
					<li>
						<a href="https://cczoo.readthedocs.io/en/latest/Solutions/tensorflow-serving-cluster/index.html"><span>TensorFlow Serving Cluster PPML&nbsp;</span></a> 
					</li>
					<li>
						<a href="https://cczoo.readthedocs.io/en/latest/Solutions/horizontal-federated-learning/hfl.html"><span>Horizontal Federated Learning&nbsp;</span></a> 
					</li>
					<li>
						<a href="https://cczoo.readthedocs.io/en/latest/Solutions/grpc-ra-tls/index.html"><span>RA-TLS Enhanced gRPC</span></a> 
					</li>
					<li>
						<a href="https://cczoo.readthedocs.io/en/latest/Solutions/vertical-federated-learning/vfl.html" target="_blank">Vertical Federated Learning</a> 
					</li>
				</ul>
			</td>
		</tr>
	</tbody>
</table>

---

## Microsoft Azure

Microsoft Azure [DCsv3-series](https://docs.microsoft.com/en-us/azure/virtual-machines/dcv3-series) instances support Intel® SGX encrypted computing technology.

The following is the configuration of the DCsv3-series instance used:

<table border="1" cellpadding="1" cellspacing="1" style="width:500px;">
	<tbody>
		<tr>
			<td colspan="2">
				<strong>&nbsp; &nbsp; Public Cloud</strong>
			</td>
			<td><strong>Microsoft Azure</strong>
			</td>
		</tr>
		<tr>
			<td rowspan="5" style="text-align: left;">
				<p>&nbsp;
				</p>
				<p><strong>Instance&nbsp;</strong>
				</p>
			</td>
			<td style="text-align:left;">
				<span>Type</span>
			</td>
			<td>
				<div>
					<span>Standard_DC16s_v3</span>
				</div>
			</td>
		</tr>
		<tr>
			<td style="text-align:left;">
				<span>Kernel</span>
			</td>
			<td>
				<div>
					<span>5.13.0-1031-azure</span>
				</div>
			</td>
		</tr>
		<tr>
			<td style="text-align:left;">
				<span>OS</span>
			</td>
			<td>
				<span>Ubuntu Server 20.04 LTS - Gen2</span>
			</td>
		</tr>
		<tr>
			<td style="text-align:left;">
				<span>Memory</span>
			</td>
			<td>
				<span>128G (64G EPC Memory)</span>
			</td>
		</tr>
		<tr>
			<td style="text-align:left;">
				<span>vCPU</span>
			</td>
			<td>
				<span>16</span>
			</td>
		</tr>
		<td colspan="2">
			<br />
			<br />
			<br />
			<strong>Validated Solution&nbsp;</strong>
		</td>
			<td>
				<ul>
					<li>
						<a href="https://cczoo.readthedocs.io/en/latest/Solutions/horizontal-federated-learning/hfl.html"><span>Horizontal Federated Learning&nbsp;</span></a>
					</li>
				</ul>
			</td>
		</tr>
	</tbody>
</table>
