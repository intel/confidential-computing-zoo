
# TruCon API Documentation
This document provides the API specifications for the TruCon project, which includes the `tc_api`, `trust_log`, and `as_router` components. Each section describes the endpoints, request and response formats, and any relevant notes for using these APIs.

## tc_api API Specification

This specification defines the API endpoints corresponding to the tool of `tc_api`, which is used to manage the build, package, launch, deployment and attesation of applications runtime in a secure and auditable manner. 

### Build and Package APIs

#### Build and Package
**Endpoint:**  
`POST /api/build-package`

**Description:**  
Submit a request to build and package an application, including Dockerfile, binaries, configs, and optional signing and encryption. 
The request must include the Dockerfile and can optionally include the application binary, configuration files, and additional data files, and the build process can be signed and encrypted. The request is asynchronous, and the build result can be queried later. This process uses tools like Docker, consign, and syft to build the container image and generate the Software Bill of Materials (SBOM). The build process shall create a container image and an SBOM in SPDX format, while also optionally encrypting the package and signing it with a private key. The resulting image and SBOM can be published to a container registry at later stage. 
**Request:**
```json
{
  "dockerfile": "<file>",           
  "app_binary": "<file>",           
  "configs": ["file1", "file2"],   
  "data": ["file3"],                
  "sign_key": "<private_key.pem>",
  "cert": "<cert.pem>",            
  "encrypt": true,               
  "user_id": "user-001"           
}
````
**Response:**

```json
{
  "build_id": "bld-######",       
  "status": "submitted",          
}
```

---

#### Build Result Query

**Endpoint:**
`GET /api/build-result/{build_id}`

**Description:**
Query the status and results of a previously submitted build request.

**Response:**

```json
{
  "build_id": "bld-8de9932",           
  "status": "success",                 
  "image_id": "sha256:abcd1234",        
  "sbom_url": "https://.../sbom.json",  
  "image_url": "docker.io/myrepo/secure-app", 
  "cert_url": "https://.../cert.pem",  
}
```

---

#### Sign and Publish Image and SBOM

**Endpoint:**
`PUT /api/publish-package`

**Description:**
Sign and publish the built container image and associated SBOM (Software Bill of Materials) to the registry. The request includes the image ID, user ID, and optional metadata as user defined tags and description. In this procedure, the image and SBOM are signed with the user's private key and published to the specified container registry. The response includes the status of the publish operation and any relevant URLs for accessing the published artifacts.
Aligning with security policies, in addition to publishing image and sbom to container registry, this procedure shall invovle below two addtional steps: 
- Push the key to ecrypt the image as the certificate to verifying the image signature to the Key Broker Service (KBS) and Remote Verification Policy Service (RVPS). This is used to manage key usage policies, such as decryption, verifying signatures. The request includes the image ID, user ID, and policy details for the key.
- Publish the build logs or evidence to the Transparent Log System, which is used for auditing and verification purposes. This ensures that all actions taken during the build and publish process are logged in a tamper-proof manner.
**Request:**

```json
{
  "image_id": "sha256:abcd1234",   
  "user_id": "user-001",          
  "log_evidence": true,        
  "metadata": {
    "tags": ["latest"],             
    "description": "Secure application image",
    ... 
  }
}
```

**Response:**

```json
{
  "status": "success",                
  "image_url": "docker.io/myrepo/secure-app:latest",
  "sbom_url": "https://.../sbom.json", 
  "log_id": "xxxxxxxxxxxxx"      
}
```
log_id format: [type]-[id], where type is the type of log, and uuid is the unique identifier for the log entry. The type can be one of the following:
 - tx-<transaction_id> - for transaction log
 - uuid-<transparent_log_uuid> - for transparent log, mapping to entry_uuid


---

### Launch and Deployment

#### Launch Request

**Endpoint:**
`POST /api/deploy-launch`

**Description:**
Request to deploy and launch an application image on specified worker nodes with optional attestation, the request triggers the deployment and launch process of a container image on specified worker nodes. It includes the image URL, image ID, SBOM URL for verification, user ID, and whether attestation is required. The request can also specify a list of worker nodes where the application should be launched. The response includes a unique launch ID for tracking the request status. This process is responsible for pulling the container image from the registry, verifying its signature and SBOM, and launching it securely inside the CVM (Confidential Virtual Machine). It also supports secure upgrades of the container during runtime. 

The launch request is asynchronous, and the status can be queried later.

**Request:**

```json
{
  "image_url": "docker.io/secure/app:latest",    
  "image_id": "sha256:abcd1234",              
  "sbom_url": "https://registry.example.com/sbom.json", 
  "user_id": "user-001",                           
  "attestation_required": true,                    
}
```

**Response:**

```json
{
  "launch_id": "launch-#######",       
  "status": "initiated"                
}
```

---

#### Launch Result Query

**Endpoint:**
`GET /api/launch-result/{launch_id}`

**Description:**
Query the results and status of a launched application.

**Response:**

```json
{
  "launch_id": "launch-######",           
  "status": "success",                     
  "validation": "passed",                  
  "attestation": "trusted",             
  "log_id": "xxxxxxxxxxxxx",              
  "instance_id": [                        
    "inst-#####1",
    "inst-#####2"
  ]
}
```
log_id format: [type]-[id], where type is the type of log, and uuid is the unique identifier for the log entry. The type can be one of the following:
 - tx-<transaction_id> - for transaction log
 - uuid-<transparent_log_uuid> - for transparent log, mapping to entry_uuid

### Attestation

`tc_api` targets to provide endpoints for attestation-related operations, including verifying quotes, checking service status, and fetching quotes. In this stage, it is recommended to use the `as_router` service for attestation-related operations, which provides a unified API for attestation requests and responses. 

---

## trust_log API Specification

This specification defines the API for trust log wrapper, which is a wrapper around the Transparent Log System, providing a secure and auditable logging mechanism for the TruCon workflow. It ensures that all actions taken during the build, deployment, and attestation processes are logged in a tamper-proof manner.

### Prepare logging entry

Create a new prepared entry container. No data is yet committed to the transparency log. This is the first step in creating a log entry. 

**Endpoint:**
```
POST /v1/log-entry:prepare
```

**Request**

```json
{
  "stage": "build",
  "parent_entry_uuid": "108e9186e8c5677a638bc681c1c518c111ed69a4cef4613d7e2c34a9236c97eb384ba606463224fe",
  "metadata": { 
    "actor": { "id": "builder-01", "type": "service", "name": "TruCon Builder" },
    "description": "Build and package application",
    "project": "alpha",
    "version": "1.0.0"
  }
}
```

**Response**

```json
{
  "id": "le_3kP8yCw1k5vE", // Unique ID for the prepared log entry, this ID shall be only valid within local system until the entry is committed
  "status": "prepared",
  "created_at": "2025-08-14T07:12:02Z"
}
```

### Insert logging item
Append one or more items to a prepared entry in order. Items become part of the pending entry but are not globally committed yet. The item format shall be defined according to actual needs or is out of scope of this specification. The item can be any data that needs to be logged, such as build artifacts, SBOM, program logs or attestation reports. Each item should have a unique ID and a timestamp. The `type` field indicates the type of the item, which can be used to filter or query items later.

**Endpoint:**
```
POST /v1/log-entry/{id}/items
```

**Request**

```json
{
  "items": [  //The format of the item shall be defined according to actual needs, here just putting some examples
    {
      "type": "artifact.digest",
      "timestamp": "2025-08-14T07:12:10Z",
      "content_type": "application/json",
      "payload": { "image": "oci://registry/acme/app@sha256:…", "digest": "sha256:…" },
      "content_sha256": "e3b0c4…",
      "references": [ { "kind": "build", "uri": "urn:ci:run/12345" } ],
      "signature": { "algo": "ed25519", "key_id": "k-1", "sig": "base64…" }
    },
    {
      "type": "slsa.provenance",
      "timestamp": "2025-08-14T07:12:12Z",
      "content_type": "application/json",
      "payload": { "slsaVersion": "1.0", "builder": "trucon" },
      "content_sha256": "a94a8f…"
    },
    {
      "id": "item-003",
      "type": "attestation.report",
      "timestamp": "2025-08-14T07:12:15Z",
      "content_type": "application/json",
      "payload": {
        "attestor": "trustee-service",
        "target": "oci://registry/acme/app@sha256:abcd1234ef567890...",
        "policy": "integrity-check-v1",
        "result": "pass",
        "evidence": {
          "hash": "sha256:abcd1234ef567890...",
          "signature": "MEUCIQDh..."
        },
        "valid_until": "2025-09-14T07:12:15Z"
      },
      "content_sha256": "b94d27b9934d3e08a52e52d7da7dabfa..."
    },
    {
      "id": "item-004",
      "type": "execution.log",
      "timestamp": "2025-08-14T07:12:20Z",
      "content_type": "text/plain",
      "payload": "INFO 2025-08-14T07:12:10Z Build started\nINFO 2025-08-14T07:12:12Z Fetching dependencies\nWARN 2025-08-14T07:12:14Z Deprecated API used\nINFO 2025-08-14T07:12:18Z Build completed successfully",
      "references": [
        { "kind": "build", "uri": "urn:ci:run/12345" }
      ],
      "content_sha256": "2c26b46b68ffc68ff99b453c1d304134..."
    }
  ]
}
```

**Response**

```json
{
  "id": "le_3kP8yCw1k5vE",
  "status": "prepared",
  "items_count": 2,
}
```
---

### Commit logging entry
Commit the entry into the underlying Transparent Log. After commit, the entry becomes immutable and globally auditable.

**Endpoint:**
```
POST /v1/log-entry/{id}:commit
```

**Request:**

```
{
    "signature_policy": "true", // Optional, defines the signature policy for the entry
}
```

**Response**

```json
{
  "uuid": "le_3kP8yCw1k5vE",
  "status": "committed",
  "items_count": 2,
  "transparency_log": {
    "entry_uuid": "108e9186e8c5677a638bc681c1c518c111ed69a4cef4613d7e2c34a9236c97eb384ba606463224e7" // Unique ID of the committed entry in the Transparent Log"
    ...
  }
}
```

---
### Query logging entry from transparency log

Retrieve a committed log entry from the Transparent Log by its unique ID. This allows for auditing and verification of the logged actions.

**Endpoint:**
```
GET /v1/log-entries/{entry_uuid}
```

**Response:**

```json
{
  "entry_uuid": "108e9186e8c5677a638bc681c1c518c111ed69a4cef4613d7e2c34a9236c97eb384ba606463224e7",
  "status": "committed",
  "created_at": "2025-08-14T07:12:02Z",
  "items": [
    {
      "type": "artifact.digest",
      "timestamp": "2025-08-14T07:12:10Z",
      "content_type": "application/json",
      "payload": { "image": "oci://registry/acme/app@sha256:…", "digest": "sha256:…" },
      "content_sha256": "e3b0c4…",
      "references": [ { "kind": "build", "uri": "urn:ci:run/12345" } ],
      "signature": { "algo": "ed25519", "key_id": "k-1", "sig": "base64…" }
    },
    {
      "type": "slsa.provenance",
      "timestamp": "2025-08-14T07:12:12Z",
      "content_type": "application/json",
      "payload": { "slsaVersion": "1.0", "builder": "trucon" },
      "content_sha256": "a94a8f…"
    }
  ]
}
```

---

## as_router API Specification

This specification defines the MCP-sytle API endpoints corresponding to the attestation-related tools exposed by `as_router`. `as_router` is responsible for: 
- Handling attestation requests and responses
- Interacting with the underlying attestation services
- Providing a unified API for the TruCon workflow as well as other extensible scenarios, enabling future use as a more general MCP-style service beyond the current scope.
In its design, `as_router` supports both STDIO and Server-Sent Events (SSE) based APIs for processing attestation requests and responses. 


### Configuration

#### Supported Providers 

| Provider  | Description                 |
| --------- | --------------------------- |
| `alibaba` | Alibaba attestation service |
| `trustee` | Trustee attestation service |


#### Supported TEE Types

| TEE Type | Description                               |
| -------- | ----------------------------------------- |
| `tdx`    | Intel Trust Domain Extensions             |
| `sgx`    | Intel SGX                                 |
| `all`    | Aggregate query across all supported TEEs |



### `call_tool` Endpoint
The `call_tool` endpoint is used to invoke specific attestation tools with the required parameters. Supported operations inculde:
- verify_quote
- get_service_status
- supported_tee_types
- fetch_quote
- parse_quote

#### verify_quote

Verify an attestation quote using a specified provider.

**Input Schema**

```json
{
  "provider": "alibaba | trustee | custom", //
  "service_url": "string (optional, for custom providers)",
  "quote": "string (Base64 encoded attestation quote)",
  "nonce": "string (optional)"
}
```

**Output Schema**

```json
{
    "provider": "alibaba | trustee",
    "format": "jwt | json",
    "data": {
      "jwt": "string (JWT/JWS encoded attestation result)",
      "raw_base64": "string (Base64 encoded raw binary quote)",
      "vendor_specific": {
        "nonce": "string (optional)",
        "signature": "string (Base64 encoded, optional)",
        "claims": {
          /* provider-specific claims, e.g. mrenclave, mrsigner, report_data */
        }
    } 
}
```

**Example Request**

```json
{
  "method": "call_tool",
  "params": {
    "name": "verify_quote",
    "arguments": {
      "provider": "alibaba",
      "quote": "BASE64_QUOTE",
      "nonce": "123456"
    }
  },
  "id": "req-001"
}
```

**Example Response**

```json
{
  "id": "req-001",
  "content": [
    {
      "type": "text",
      "text": {
        "provider": "alibaba",
        "format": "jwt",
        "data": {
          "jwt": "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9...",
          "raw_base64": null,
          "vendor_specific": null
        }
      }
    }
  ]
}

```

---

#### get_service_status

Retrieve the operational status of an attestation service.

**Input Schema**

```json
{
  "provider": "alibaba | trustee | custom",
  "service_url": "string (optional, for custom AS providers)"
}
```
***Output Schema***

```json
{
  "provider": "alibaba | trustee | custom",
  "service_url": "string (optional, for custom AS providers)",
  "status": "available | unavailable",
  "uptime": "number (seconds since last restart, optional)"
}
```

**Example Request**

```json
{
  "method": "call_tool",
  "params": {
    "name": "get_service_status",
    "arguments": {
      "provider": "alibaba"
    }
  },
  "id": "req-002"
}
```

**Example Response**

```json
{
  "id": "req-002",
  "content": [
    {
      "type": "json",
      "data": {
        "provider": "alibaba",
        "service_url": null,
        "status": "available",
        "uptime": 12345
      }
    }
  ]
}

```

---

#### supported_tee_types

Query supported TEE technologies from providers.

**Input Schema**

```json
{
  "technology": "string (one or multiple TEE types separated by '|', e.g., 'tdx', 'sgx', 'tdx|sgx', or 'all')"
}
```

**Behavior**

* If `technology` is `all`: returns supported TEE list from all providers.
* Otherwise: checks whether the given TEE type is supported by each provider.

**Example Request**

```json
{
  "method": "call_tool",
  "params": {
    "name": "supported_tee_types",
    "arguments": {
      "technology": "tdx | sgx | all"
    }
  },
  "id": "req-003"
}
```

**Example Response**

```json
{
    "technology": "tdx | sgx ",
    "supported": true
}

```

---

#### fetch_quote

Retrieve an attestation quote from the local system.

**Input Schema**

```json
{
  "teeType": "tdx | sgx (optional, defaults to tdx)",
  "nonce": "string (optional)",
  "userData": "string (optional)"
}
```
***Output Schema***

```json
{
  "quote": "string (Base64 encoded attestation quote)",
  "teeType": "tdx | sgx",
  "nonce": "string (optional)"
}
```

**Status**

* Currently a placeholder; implementation of `fetchLocalQuote()` is pending.


---

#### parse_quote

Parse a binary attestation quote into a structured JSON format.

**Input Schema**

```json
{
   "quote": "string (Base64 encoded attestation quote)"
}
```

**Output Schema (placeholder)**

{
  "parsed": { /* structured representation of the quote */ }
} 

**Example Request**

```json
{
  "method": "call_tool",
  "params": {
    "name": "parse_quote",
    "arguments": {
      "quote": "BASE64_QUOTE"
    }
  },
  "id": "req-004"
}
```


### `listTools` Discovery Endpoint

It is the mandatory requirement to provide a `listTools` request to enumerate available tools and their input schemas.

**Example Request**

```json
{
  "method": "listTools",
  "id": "req-list"
}
```

**Example Response**

```json
{
  "tools": [
    {
      "name": "verify_quote",
      "description": "Verify a quote using specified attestation service",
      "inputSchema": { ... }
    },
    {
      "name": "get_service_status",
      "description": "Get status information about an attestation service",
      "inputSchema": { ... }
    },
    {
      "name": "supported_tee_types",
      "description": "Query supported TEE technologies from providers",
      "inputSchema": { ... }
    },
    {
      "name": "fetch_quote",
      "description": "Fetch an attestation quote from the local system",
      "inputSchema": { ... }
    },
    {
      "name": "parse_quote",
      "description": "Parse a binary attestation quote into structured JSON format",
      "inputSchema": { ... }
    }
  ]
}
```

---

