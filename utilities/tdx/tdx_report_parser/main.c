/*
 *
 * Copyright (c) 2023 Intel Corporation
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 */

#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
#include <time.h>

#include "tdx_attest.h"
#include "getopt.hpp"

#define PACKED __attribute__((__packed__))

#define SIZE_OF_SHA256_HASH_IN_QWORDS 4
#define SIZE_OF_SHA384_HASH_IN_QWORDS 6
#define SIZE_OF_SHA384_HASH_IN_BYTES (SIZE_OF_SHA384_HASH_IN_QWORDS << 3)
#define SIZE_OF_TD_REPORT_STRUCT_IN_BYTES 1024

#define HEX_DUMP_SIZE   16
#define MAX_ROW_SIZE    70

#define TDX_ATTR_DEBUG_MASK             (1UL << 0)
#define TDX_ATTR_SEPT_VE_DISABLE_MASK   (1UL << 28)

struct argparser {
    int mode;
    const char* path;
    argparser() {
        mode = getarg(1, "-m", "--mode"); // 0: gen, 1: gen+parse, 2: parse
        path = getarg("tdx_report.data", "-p", "--path");
    };
};

typedef union measurement_u {
    uint64_t qwords[SIZE_OF_SHA384_HASH_IN_QWORDS];
    uint8_t  bytes[SIZE_OF_SHA384_HASH_IN_BYTES];
} measurement_t;

// REPORTTYPE indicates the reported Trusted Execution Environment (TEE) type, sub-type and version.
typedef union PACKED td_report_type_s {
    struct {
        //
        // Trusted Execution Environment (TEE) Type:
        //      0x00:   SGX
        //      0x7F-0x01:  Reserved (TEE implemented by CPU)
        //      0x80:   Reserved (TEE implemented by SEAM module)
        //      0x81:   TDX
        //      0xFF-0x82:  Reserved (TEE implemented by SEAM module)
        //
        uint8_t type;
        uint8_t subtype;        // TYPE-specific subtype
        uint8_t version;        // TYPE-specific version.
        uint8_t reserved;       // Must be zero
    };
    uint32_t raw;
} td_report_type_t;

#define CPUSVN_SIZE                       16 // < CPUSVN is a 16B Security Version Number of the CPU.
#define SIZE_OF_REPORTDATA_IN_BYTES       64
#define SIZE_OF_REPORTMAC_STRUCT_IN_BYTES 256

// REPORTMACSTRUCT is common to all TEEs (SGX and TDX).
typedef struct PACKED report_mac_struct_s {
    td_report_type_t  report_type;                  // Type Header Structure
    uint8_t           reserved_0[12];               // < Must be 0
    uint8_t           cpusvn[CPUSVN_SIZE];  // < CPU SVN
    // SHA384 of TEETCBINFO for TEEs implemented using a SEAM
    uint8_t          tee_tcb_info_hash[SIZE_OF_SHA384_HASH_IN_QWORDS * 8];
    //SHA384 of TEEINFO, which is a TEE-specific info structure (TDINFO or SGXINFO), or 0 if no TEE is represented
    uint8_t          tee_info_hash[SIZE_OF_SHA384_HASH_IN_QWORDS * 8];
    // A set of data used for communication between the caller and the target.
    uint8_t           report_data[SIZE_OF_REPORTDATA_IN_BYTES];
    uint8_t           reserved_1[32];
    uint8_t          mac[SIZE_OF_SHA256_HASH_IN_QWORDS * 8]; // < The MAC over the REPORTMACSTRUCT with model-specific MAC
} report_mac_struct_t;

#define SIZE_OF_TEE_TCB_SVN_IN_BYTES         16
typedef struct PACKED tee_tcb_info_s {
    //
    // Indicates TEE_TCB_INFO fields which are valid.
    // - 1 in the i-th significant bit reflects that the field starting at offset (8 * i)
    // - 0 in the i-th significant bit reflects that either no field starts at offset (8 * i)
    //   or that field is not populated and is set to zero.
    //
    uint64_t       valid;
    uint8_t        tee_tcb_svn[SIZE_OF_TEE_TCB_SVN_IN_BYTES];  // < TEE_TCB_SVN Array
    measurement_t  mr_seam;  // < Measurement of the SEAM module
    //
    // Measurement of SEAM module signer if non-intel SEAM module was loaded
    //
    measurement_t  mr_signer_seam;
    uint64_t       attributes;  // < Additional configuration ATTRIBUTES if non-intel SEAM module was loaded
    uint8_t        reserved[128];  // Must be 0
} tee_tcb_info_t;

#define NUM_OF_RTMRS                    4
#define SIZE_OF_TD_INFO_STRUCT_IN_BYTES 512

//
// @struct td_info_s
//
// @brief TDINFO_STRUCT is the TDX-specific TEEINFO part of TDGMRREPORT.
//
// It contains the measurements and initial configuration of the TD that was locked at initialization,
// and a set of measurement registers that are run-time extendible.
// These values are copied from the TDCS by the TDGMRREPORT function.
//
typedef struct PACKED td_info_s {
    uint64_t       attributes;  // < TD’s ATTRIBUTES
    uint64_t       xfam;                // < TD’s XFAM
    measurement_t  mr_td;               // < Measurement of the initial contents of the TD
    //
    // 48 Software defined ID for additional configuration for the software in the TD
    //
    measurement_t  mr_config_id;
    measurement_t  mr_owner;    // < Software defined ID for TD’s owner
    //
    // Software defined ID for owner-defined configuration of the guest TD,
    // e.g., specific to the workload rather than the runtime or OS.
    //
    measurement_t  mr_owner_config;
    // measurement_t  rtmr[NUM_OF_RTMRS]; // <  Array of NUM_RTMRS runtime extendable measurement registers
        measurement_t  rtmr0;
        measurement_t  rtmr1;
        measurement_t  rtmr2;
        measurement_t  rtmr3;
    uint8_t        reserved[112];
} td_info_t;

//
// @struct td_report_t
//
// @brief TDREPORT_STRUCT is the output of the TDGMRREPORT function.
//
// If is composed of a generic MAC structure, a SEAMINFO structure and
// a TDX-specific TEE info structure.
//
typedef struct PACKED td_report_s {
    report_mac_struct_t  report_mac_struct; // < REPORTMACSTRUCT for the TDGMRREPORT
    //
    // Additional attestable elements in the TD’s TCB not reflected in the REPORTMACSTRUCT.CPUSVN.
    // Includes the SEAM measurements.
    //
    tee_tcb_info_t       tee_tcb_info;
    td_info_t            td_info;                       // < TD’s attestable properties
} td_report_t;

static void print_hex_dump(const char *title, const char *prefix_str,
                       const uint8_t *buf, int len) {
    const uint8_t *ptr = buf;
    int i, rowsize = HEX_DUMP_SIZE;

    if (!len || !buf) {
        return;
    }

    fprintf(stdout, "\t\t%s", title);

    for (i = 0; i < len; i++) {
        if (!(i % rowsize))
            fprintf(stdout, "\n%s%.8x:", prefix_str, i);
        if (ptr[i] <= 0x0f)
            fprintf(stdout, " 0%x", ptr[i]);
        else
            fprintf(stdout, " %x", ptr[i]);
    }

    fprintf(stdout, "\n");
}

void gen_report_data(uint8_t *reportdata) {
    int i;
    srand(time(NULL));
    for (i = 0; i < TDX_REPORT_DATA_SIZE; i++)
        reportdata[i] = rand();
}

void print_measurement_t(const char *name, const measurement_t m) {
    printf("%s: ", name);
    for (int i = 0; i < SIZE_OF_SHA384_HASH_IN_BYTES; i++) {
        printf("%02x", m.bytes[i]);
    }
    putchar('\n');
}

void print_td_info_t(const td_info_t* td_info) {
    printf("TD info\n");
    printf("attributes: 0x%016lx ", td_info->attributes);
    printf("(%s ", td_info->attributes & TDX_ATTR_DEBUG_MASK ? "DEBUG": "NO_DEBUG");
    printf("%s", td_info->attributes & TDX_ATTR_SEPT_VE_DISABLE_MASK ? "SEPT_VE_DISABLE": "NO_SEPT_VE_DISABLE");
    printf(")\n");

    printf("xfam: 0x%016lx\n", td_info->xfam);
    print_measurement_t("mr_td", td_info->mr_td);
    print_measurement_t("mr_config_id", td_info->mr_config_id);
    print_measurement_t("mr_owner", td_info->mr_owner);
    print_measurement_t("mr_owner_config", td_info->mr_owner_config);
    print_measurement_t("rtmr0", td_info->rtmr0);
    print_measurement_t("rtmr1", td_info->rtmr1);
    print_measurement_t("rtmr2", td_info->rtmr2);
    print_measurement_t("rtmr3", td_info->rtmr3);
}

void dump_report(const char* path, td_report_t &data) {
    FILE *fp = fopen(path, "w+");
    if (!fp) {
        printf("dump_report failed!\n");
        exit(-1);
    } else {
        fwrite(&data, sizeof(data), 1, fp);
    }
    fclose(fp);
}

td_report_t load_report(const char* path) {
    td_report_t data = {{0}};
    FILE *fp = fopen(path, "r");
    if (!fp) {
        printf("load_report failed!\n");
        exit(-1);
    } else {
        fread(&data, sizeof(data), 1, fp);
    }
    fclose(fp);
    return data;
}

int main(int argc, char *argv[]) {
    argparser args;

    uint32_t quote_size = 0;
    tdx_report_data_t report_data = {{0}};
    td_report_t tdx_report = {{0}};
    tdx_uuid_t selected_att_key_id = {0};
    uint8_t *p_quote_buf = NULL;
    FILE *fptr = NULL;


    if (args.mode < 0 || args.mode > 2) {
        fprintf(stderr, "\nWrong mode!\n");
        exit(-1);
    }

    if (args.mode == 0 || args.mode == 1) {
        gen_report_data(report_data.d);
        // print_hex_dump("\n\t\tTDX report data\n", " ", report_data.d, sizeof(report_data.d));

        if (TDX_ATTEST_SUCCESS != tdx_att_get_report(&report_data, (tdx_report_t *)&tdx_report)) {
            fprintf(stderr, "\nFailed to get the report\n");
            exit(-1);
        }
    }

    if (args.path != "") {
        if (args.mode == 0) {
            dump_report(args.path, tdx_report);
        } else if (args.mode == 2) {
            tdx_report = load_report(args.path);
        }
    }

    if (args.mode == 1 || args.mode == 2) {
        print_td_info_t(&tdx_report.td_info);
    }

    return 0;
}

