/*
 *
 *Copyright (c) 2022 Intel Corporation
 *
 *Licensed under the Apache License, Version 2.0 (the "License");
 *you may not use this file except in compliance with the License.
 *You may obtain a copy of the License at
 *
 *    http://www.apache.org/licenses/LICENSE-2.0
 *
 *Unless required by applicable law or agreed to in writing, software
 *distributed under the License is distributed on an "AS IS" BASIS,
 *WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *See the License for the specific language governing permissions and
 *limitations under the License.
 *
 */

// #include <grpcpp/security/sgx/sgx_ra_tls_impl.h>
#include <grpcpp/security/sgx/sgx_ra_tls_context.h>
#include <grpcpp/security/sgx/sgx_ra_tls_utils.h>

namespace grpc {
namespace sgx {

#include <openssl/evp.h>
#include <openssl/rsa.h>
#include <openssl/x509.h>
#include <openssl/x509v3.h>
#include <openssl/sha.h>
#include <openssl/pem.h>
#include <openssl/asn1.h>

const char *RA_TLS_SHORT_NAME = "RA-TLS";
const char *RA_TLS_LONG_NAME = "RA-TLS Extension";

struct ra_tls_context _ctx_;

std::vector<std::string> generate_key_cert(
    int (*generate_quote)(
        uint8_t **quote_buf, uint32_t &quote_size, uint8_t *hash)) {
    char private_key_pem[CERT_KEY_MAX_SIZE],
                cert_pem[CERT_KEY_MAX_SIZE];

    int32_t ret = -1;
    uint32_t quote_size = 0;
    uint8_t *quote_buf = nullptr;

    BIGNUM *e = BN_new();
    BN_set_word(e, RSA_F4);
    RSA *rsa = RSA_new();
    RSA_generate_key_ex(rsa, 2048, e, nullptr);

    EVP_PKEY *pkey = EVP_PKEY_new();
    EVP_PKEY_assign_RSA(pkey, rsa);

    X509 *x509 = X509_new();

    ASN1_INTEGER_set(X509_get_serialNumber(x509), 1);
    X509_gmtime_adj(X509_get_notBefore(x509), 0);
    X509_gmtime_adj(X509_get_notAfter(x509), 630720000L);
    X509_set_pubkey(x509, pkey);

    X509_NAME *name = X509_NAME_new();
    // X509_NAME *name = X509_get_subject_name(x509);
    X509_NAME_add_entry_by_txt(name, "C",  MBSTRING_ASC,
                               (uint8_t *)"CN", -1, -1, 0);
    X509_NAME_add_entry_by_txt(name, "O",  MBSTRING_ASC,
                               (uint8_t *)"Intel Inc.", -1, -1, 0);
    X509_NAME_add_entry_by_txt(name, "CN", MBSTRING_ASC,
                               (uint8_t *)"localhost", -1, -1, 0);
    X509_set_subject_name(x509, name);
    X509_set_issuer_name(x509, name);

    size_t key_size = i2d_PUBKEY(pkey, 0);
    uint8_t *public_key = nullptr;
    // size_t pubkey_size = i2d_PUBKEY(pkey, &public_key);
    size_t pubkey_size = i2d_X509_PUBKEY(X509_get_X509_PUBKEY(x509), &public_key);

    if (pubkey_size != key_size) {
        grpc_printf("get public key failed!");
    }

    BIO *bio = BIO_new(BIO_s_mem());
    if (!bio) {
        grpc_printf("create bio failed!");
    }

    ret = PEM_write_bio_RSAPrivateKey(bio, rsa, nullptr, nullptr, 0, nullptr, nullptr);
    if (ret == 0) {
        grpc_printf("write private key failed!");
    }

    ret = BIO_read(bio, private_key_pem, bio->num_write);
    if (ret == 0) {
        grpc_printf("read private key failed!");
    }

    uint8_t hash[SHA256_DIGEST_LENGTH];
    SHA256_CTX sha256;
    SHA256_Init(&sha256);
    SHA256_Update(&sha256, public_key, key_size);
    SHA256_Final(hash, &sha256);

    ret = generate_quote(&quote_buf, quote_size, hash);
    if (ret == 0) {
        grpc_printf("generate quote failed!\n");
    }

    int nid = OBJ_create("1.2.840.113741.1", RA_TLS_SHORT_NAME, RA_TLS_LONG_NAME);
    ASN1_OBJECT* obj = OBJ_nid2obj(nid);
    ASN1_OCTET_STRING* data = ASN1_OCTET_STRING_new();
    ASN1_OCTET_STRING_set(data, quote_buf, quote_size);

    X509_EXTENSION* ext = X509_EXTENSION_create_by_OBJ(nullptr, obj, 0, data);
    X509_add_ext(x509, ext, -1);
    X509_sign(x509, pkey, EVP_sha1());

    BIO *cert_bio = BIO_new(BIO_s_mem());
    if (!cert_bio) {
        grpc_printf("create crt bio failed!");
    }

    ret = PEM_write_bio_X509(cert_bio, x509);
    if (ret == 0) {
        grpc_printf("read crt bio failed!");
    }

    ret = BIO_read(cert_bio, cert_pem, cert_bio->num_write);
    if (ret == 0) {
        grpc_printf("read pem cert failed!");
    }

    std::vector<std::string> key_cert;
    key_cert.emplace_back(std::string((char*) private_key_pem));
    key_cert.emplace_back(std::string((char*) cert_pem));

    BIO_free(bio);
    BIO_free(cert_bio);
    EVP_PKEY_free(pkey);
    check_free(quote_buf);
    return key_cert;
}

int parse_quote(X509 *x509, uint8_t **quote, uint32_t &quote_size) {
    int ret = -1;
    // STACK_OF(X509_EXTENSION) exts = x509->cert_info->extensions;
    auto exts = X509_get0_extensions(x509);
    if (exts) {
        int ext_num = sk_X509_EXTENSION_num(exts);
        for (int i = 0; i < ext_num; i++) {
            X509_EXTENSION *ext = sk_X509_EXTENSION_value(exts, i);
            ASN1_OBJECT *obj = X509_EXTENSION_get_object(ext);
            int nid = OBJ_obj2nid(obj);
            if (nid != NID_undef) {
                const char *ln = OBJ_nid2ln(nid);
                if (memcmp(RA_TLS_LONG_NAME, ln, sizeof(RA_TLS_LONG_NAME)) == 0) {
                    BIO *ext_bio = BIO_new(BIO_s_mem());
                    quote_size = i2d_ASN1_OCTET_STRING(ext->value, quote);
                    *quote = *quote + 4;
                    quote_size = quote_size - 4;
                    ret = 0;
                    BIO_free(ext_bio);
                }
            }
        }
    }

    return ret;
}

int verify_pubkey_hash(X509 *x509, uint8_t *pubkey_hash, uint32_t hash_size) {
    int32_t ret = -1;
    uint8_t *public_key = nullptr;

    // EVP_PKEY *pkey = X509_get_pubkey(x509);
    // size_t key_size = EVP_PKEY_bits(pkey)/8;

    auto key_size = i2d_X509_PUBKEY(X509_get_X509_PUBKEY(x509), &public_key);

    uint8_t hash[hash_size];
    SHA256_CTX sha256;
    SHA256_Init(&sha256);
    SHA256_Update(&sha256, public_key, key_size);
    SHA256_Final(hash, &sha256);

    // grpc_printf("hash size: %u, %u, %u\n", hash_size, sizeof(hash), sizeof(pubkey_hash));

    ret = memcmp(hash, pubkey_hash, hash_size);
    return ret;
}

#ifdef SGX_RA_TLS_TDX_BACKEND

ra_tls_config parse_config_json(const char* file) {
    struct ra_tls_config cfg;

    if (!check_file(file)) {
        grpc_printf("could not to find and parse file!\n");
    } else {
        class json_engine tdx_json(file);
        grpc_printf("%s\n", tdx_json.print_item(tdx_json.get_handle()));

        cfg.verify_mr_seam = tdx_json.cmp_item(tdx_json.get_item(tdx_json.get_handle(), "verify_mr_seam"), "on");
        cfg.verify_mrsigner_seam = tdx_json.cmp_item(tdx_json.get_item(tdx_json.get_handle(), "verify_mrsigner_seam"), "on");
        cfg.verify_mr_td = tdx_json.cmp_item(tdx_json.get_item(tdx_json.get_handle(), "verify_mr_td"), "on");
        cfg.verify_mr_config_id = tdx_json.cmp_item(tdx_json.get_item(tdx_json.get_handle(), "verify_mr_config_id"), "on");
        cfg.verify_mr_owner = tdx_json.cmp_item(tdx_json.get_item(tdx_json.get_handle(), "verify_mr_owner"), "on");
        cfg.verify_mr_owner_config = tdx_json.cmp_item(tdx_json.get_item(tdx_json.get_handle(), "verify_mr_owner_config"), "on");
        cfg.verify_rt_mr0 = tdx_json.cmp_item(tdx_json.get_item(tdx_json.get_handle(), "verify_rt_mr0"), "on");
        cfg.verify_rt_mr1 = tdx_json.cmp_item(tdx_json.get_item(tdx_json.get_handle(), "verify_rt_mr1"), "on");
        cfg.verify_rt_mr2 = tdx_json.cmp_item(tdx_json.get_item(tdx_json.get_handle(), "verify_rt_mr2"), "on");
        cfg.verify_rt_mr3 = tdx_json.cmp_item(tdx_json.get_item(tdx_json.get_handle(), "verify_rt_mr3"), "on");

        auto objs = tdx_json.get_item(tdx_json.get_handle(), "tdx_mrs");
        auto obj_num = std::min(cJSON_GetArraySize(objs), MESUREMENTS_MAX_SIZE);

        cfg.mrs = std::vector<ra_tls_measurement>(obj_num, ra_tls_measurement());
        for (auto i = 0; i < obj_num; i++) {
            auto obj = cJSON_GetArrayItem(objs, i);

            auto mr_seam = tdx_json.print_item(tdx_json.get_item(obj, "mr_seam"));
            memset(cfg.mrs[i].mr_seam, 0, sizeof(cfg.mrs[i].mr_seam));
            hex_to_byte(mr_seam+1, cfg.mrs[i].mr_seam, sizeof(cfg.mrs[i].mr_seam));

            auto mrsigner_seam = tdx_json.print_item(tdx_json.get_item(obj, "mrsigner_seam"));
            memset(cfg.mrs[i].mrsigner_seam, 0, sizeof(cfg.mrs[i].mrsigner_seam));
            hex_to_byte(mrsigner_seam+1, cfg.mrs[i].mrsigner_seam, sizeof(cfg.mrs[i].mrsigner_seam));

            auto mr_td = tdx_json.print_item(tdx_json.get_item(obj, "mr_td"));
            memset(cfg.mrs[i].mr_td, 0, sizeof(cfg.mrs[i].mr_td));
            hex_to_byte(mr_td+1, cfg.mrs[i].mr_td, sizeof(cfg.mrs[i].mr_td));

            auto mr_config_id = tdx_json.print_item(tdx_json.get_item(obj, "mr_config_id"));
            memset(cfg.mrs[i].mr_config_id, 0, sizeof(cfg.mrs[i].mr_config_id));
            hex_to_byte(mr_config_id+1, cfg.mrs[i].mr_config_id, sizeof(cfg.mrs[i].mr_config_id));

            auto mr_owner = tdx_json.print_item(tdx_json.get_item(obj, "mr_owner"));
            memset(cfg.mrs[i].mr_owner, 0, sizeof(cfg.mrs[i].mr_owner));
            hex_to_byte(mr_owner+1, cfg.mrs[i].mr_owner, sizeof(cfg.mrs[i].mr_owner));

            auto mr_owner_config = tdx_json.print_item(tdx_json.get_item(obj, "mr_owner_config"));
            memset(cfg.mrs[i].mr_owner_config, 0, sizeof(cfg.mrs[i].mr_owner_config));
            hex_to_byte(mr_owner_config+1, cfg.mrs[i].mr_owner_config, sizeof(cfg.mrs[i].mr_owner_config));

            auto rt_mr0 = tdx_json.print_item(tdx_json.get_item(obj, "rt_mr0"));
            memset(cfg.mrs[i].rt_mr0, 0, sizeof(cfg.mrs[i].rt_mr0));
            hex_to_byte(rt_mr0+1, cfg.mrs[i].rt_mr0, sizeof(cfg.mrs[i].rt_mr0));

            auto rt_mr1 = tdx_json.print_item(tdx_json.get_item(obj, "rt_mr1"));
            memset(cfg.mrs[i].rt_mr1, 0, sizeof(cfg.mrs[i].rt_mr1));
            hex_to_byte(rt_mr1+1, cfg.mrs[i].rt_mr1, sizeof(cfg.mrs[i].rt_mr1));

            auto rt_mr2 = tdx_json.print_item(tdx_json.get_item(obj, "rt_mr2"));
            memset(cfg.mrs[i].rt_mr2, 0, sizeof(cfg.mrs[i].rt_mr2));
            hex_to_byte(rt_mr2+1, cfg.mrs[i].rt_mr2, sizeof(cfg.mrs[i].rt_mr2));

            auto rt_mr3 = tdx_json.print_item(tdx_json.get_item(obj, "rt_mr3"));
            memset(cfg.mrs[i].rt_mr3, 0, sizeof(cfg.mrs[i].rt_mr3));
            hex_to_byte(rt_mr3+1, cfg.mrs[i].rt_mr3, sizeof(cfg.mrs[i].rt_mr3));
        };
    }

    return cfg;
}

static bool verify_measurement_internal(
                    const char* mr_seam,
                    const char* mrsigner_seam,
                    const char* mr_td,
                    const char* mr_config_id,
                    const char* mr_owner,
                    const char* mr_owner_config,
                    const char* rt_mr0,
                    const char* rt_mr1,
                    const char* rt_mr2,
                    const char* rt_mr3) {
    bool status = false;
    auto & cfg = _ctx_.cfg;
    for (auto & obj : cfg.mrs) {
        status = true;

        if (status && cfg.verify_mr_seam && \
            memcmp(obj.mr_seam, mr_seam, 32)) {
            status = false;
        }
        if (status && cfg.verify_mrsigner_seam && \
            memcmp(obj.mrsigner_seam, mrsigner_seam, 32)) {
            status = false;
        }
        if (status && cfg.verify_mr_td && \
            memcmp(obj.mr_td, mr_td, 32)) {
            status = false;
        }
        if (status && cfg.verify_mr_config_id && \
            memcmp(obj.mr_config_id, mr_config_id, 32)) {
            status = false;
        }
        if (status && cfg.verify_mr_owner && \
            memcmp(obj.mr_owner, mr_owner, 32)) {
            status = false;
        }
        if (status && cfg.verify_mr_owner_config && \
            memcmp(obj.mr_owner_config, mr_owner_config, 32)) {
            status = false;
        }
        if (status && cfg.verify_rt_mr0 && \
            memcmp(obj.rt_mr0, rt_mr0, 32)) {
            status = false;
        }
        if (status && cfg.verify_rt_mr1 && \
            memcmp(obj.rt_mr1, rt_mr1, 32)) {
            status = false;
        }
        if (status && cfg.verify_rt_mr2 && \
            memcmp(obj.rt_mr2, rt_mr2, 32)) {
            status = false;
        }
        if (status && cfg.verify_rt_mr3 && \
            memcmp(obj.rt_mr3, rt_mr3, 32)) {
            status = false;
        }
        if (status) {
            break;
        }
    }
    return status;
}

int verify_measurement(const char* mr_seam,
                       const char* mrsigner_seam,
                       const char* mr_td,
                       const char* mr_config_id,
                       const char* mr_owner,
                       const char* mr_owner_config,
                       const char* rt_mr0,
                       const char* rt_mr1,
                       const char* rt_mr2,
                       const char* rt_mr3) {
    std::lock_guard<std::mutex> lock(_ctx_.mtx);
    bool status = false;
    try {
        grpc_printf("remote attestation\n");

        if (_ctx_.cfg.verify_mr_seam) {
            grpc_printf("  |- mr_seam        :  %s\n", byte_to_hex(mr_seam, 32).c_str());
        };
        if (_ctx_.cfg.verify_mrsigner_seam) {
            grpc_printf("  |- mrsigner_seam  :  %s\n", byte_to_hex(mrsigner_seam, 32).c_str());
        };
        if (_ctx_.cfg.verify_mr_td) {
            grpc_printf("  |- mr_td     :  %s\n", byte_to_hex(mr_td, 32).c_str());
        };
        if (_ctx_.cfg.verify_mr_config_id) {
            grpc_printf("  |- mr_config_id   :  %s\n", byte_to_hex(mr_config_id, 32).c_str());
        };
        if (_ctx_.cfg.verify_mr_owner) {
            grpc_printf("  |- mr_owner       :  %s\n", byte_to_hex(mr_owner, 32).c_str());
        };
        if (_ctx_.cfg.verify_mr_owner_config) {
            grpc_printf("  |- mr_owner_config:  %s\n", byte_to_hex(mr_owner_config, 32).c_str());
        };
        if (_ctx_.cfg.verify_rt_mr0) {
            grpc_printf("  |- rt_mr0         :  %s\n", byte_to_hex(rt_mr0, 32).c_str());
        };
        if (_ctx_.cfg.verify_rt_mr1) {
            grpc_printf("  |- rt_mr1         :  %s\n", byte_to_hex(rt_mr1, 32).c_str());
        };
        if (_ctx_.cfg.verify_rt_mr2) {
            grpc_printf("  |- rt_mr2         :  %s\n", byte_to_hex(rt_mr2, 32).c_str());
        };
        if (_ctx_.cfg.verify_rt_mr3) {
            grpc_printf("  |- rt_mr3         :  %s\n", byte_to_hex(rt_mr3, 32).c_str());
        };
        if (status = verify_measurement_internal(
                                        mr_seam,
                                        mrsigner_seam,
                                        mr_td,
                                        mr_config_id,
                                        mr_owner,
                                        mr_owner_config,
                                        rt_mr0,
                                        rt_mr1,
                                        rt_mr2,
                                        rt_mr3)) {
            grpc_printf("  |- verify result  :  success\n");
        } else {
            grpc_printf("  |- verify result  :  failed\n");
        }
    } catch (...) {
        grpc_printf("unable to verify measurement!");
    }

    fflush(stdout);
    return status ? 0 : -1;
}

#else

ra_tls_config parse_config_json(const char* file) {
    struct ra_tls_config cfg;

    if (!check_file(file)) {
        grpc_printf("could not to find and parse file!\n");
    } else {
        class json_engine sgx_json(file);
        grpc_printf("%s\n", sgx_json.print_item(sgx_json.get_handle()));

        cfg.verify_mr_enclave = sgx_json.cmp_item(sgx_json.get_item(sgx_json.get_handle(), "verify_mr_enclave"), "on");
        cfg.verify_mr_signer = sgx_json.cmp_item(sgx_json.get_item(sgx_json.get_handle(), "verify_mr_signer"), "on");
        cfg.verify_isv_prod_id = sgx_json.cmp_item(sgx_json.get_item(sgx_json.get_handle(), "verify_isv_prod_id"), "on");
        cfg.verify_isv_svn = sgx_json.cmp_item(sgx_json.get_item(sgx_json.get_handle(), "verify_isv_svn"), "on");

        auto objs = sgx_json.get_item(sgx_json.get_handle(), "sgx_mrs");
        auto obj_num = std::min(cJSON_GetArraySize(objs), MESUREMENTS_MAX_SIZE);

        cfg.mrs = std::vector<ra_tls_measurement>(obj_num, ra_tls_measurement());
        for (auto i = 0; i < obj_num; i++) {
            auto obj = cJSON_GetArrayItem(objs, i);

            auto mr_enclave = sgx_json.print_item(sgx_json.get_item(obj, "mr_enclave"));
            memset(cfg.mrs[i].mr_enclave, 0, sizeof(cfg.mrs[i].mr_enclave));
            hex_to_byte(mr_enclave+1, cfg.mrs[i].mr_enclave, sizeof(cfg.mrs[i].mr_enclave));

            auto mr_signer = sgx_json.print_item(sgx_json.get_item(obj, "mr_signer"));
            memset(cfg.mrs[i].mr_signer, 0, sizeof(cfg.mrs[i].mr_signer));
            hex_to_byte(mr_signer+1, cfg.mrs[i].mr_signer, sizeof(cfg.mrs[i].mr_signer));

            auto isv_prod_id = sgx_json.print_item(sgx_json.get_item(obj, "isv_prod_id"));
            cfg.mrs[i].isv_prod_id = strtoul(isv_prod_id, nullptr, 10);

            auto isv_svn = sgx_json.print_item(sgx_json.get_item(obj, "isv_svn"));
            cfg.mrs[i].isv_svn = strtoul(isv_svn, nullptr, 10);
        };
    }

    return cfg;
}

static bool verify_measurement_internal(const char* mr_enclave,
                                        const char* mr_signer,
                                        const char* isv_prod_id,
                                        const char* isv_svn) {
    bool status = false;
    auto & cfg = _ctx_.cfg;
    if (!(cfg.verify_mr_enclave ||
        cfg.verify_mr_signer ||
        cfg.verify_isv_prod_id ||
        cfg.verify_isv_svn)) {
        status = true;
    } else {
        for (auto & obj : cfg.mrs) {
            status = true;

            if (status && cfg.verify_mr_enclave && \
                memcmp(obj.mr_enclave, mr_enclave, 32)) {
                status = false;
            }

            if (status && cfg.verify_mr_signer && \
                memcmp(obj.mr_signer, mr_signer, 32)) {
                status = false;
            }

            if (status && cfg.verify_isv_prod_id && \
                (obj.isv_prod_id != *(uint16_t*)isv_prod_id)) {
                status = false;
            }

            if (status && cfg.verify_isv_svn && \
                (obj.isv_svn != *(uint16_t*)isv_svn)) {
                status = false;
            }

            if (status) {
                break;
            }
        }
    }
    return status;
}

int verify_measurement(const char* mr_enclave, const char* mr_signer,
                       const char* isv_prod_id, const char* isv_svn) {
    std::lock_guard<std::mutex> lock(_ctx_.mtx);
    bool status = false;
    try {
        grpc_printf("remote attestation\n");

        if (_ctx_.cfg.verify_mr_enclave) {
            grpc_printf("  |- mr_enclave     :  %s\n", byte_to_hex(mr_enclave, 32).c_str());
        };

        if (_ctx_.cfg.verify_mr_signer) {
            grpc_printf("  |- mr_signer      :  %s\n", byte_to_hex(mr_signer, 32).c_str());
        };

        if (_ctx_.cfg.verify_isv_prod_id) {
            grpc_printf("  |- isv_prod_id    :  %hu\n", *((uint16_t*)isv_prod_id));
            };

        if (_ctx_.cfg.verify_isv_svn) {
            grpc_printf("  |- isv_svn        :  %hu\n", *((uint16_t*)isv_svn));
        };

        if (status = verify_measurement_internal(
                        mr_enclave, mr_signer, isv_prod_id, isv_svn)) {
            grpc_printf("  |- verify result  :  success\n");
        } else {
            grpc_printf("  |- verify result  :  failed\n");
        }
    } catch (...) {
        grpc_printf("unable to verify measurement!");
    }

    fflush(stdout);
    return status ? 0 : -1;
}

#endif

} // namespace sgx
} // namespace grpc
