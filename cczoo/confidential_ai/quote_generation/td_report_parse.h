// Copyright (c) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
#include <time.h>
#include <string.h>
#include "tdx_attest.h"

#include <stdint.h>
#define PACKED                  __attribute__((__packed__))

#define SIZE_OF_SHA256_HASH_IN_QWORDS 4
#define SIZE_OF_SHA384_HASH_IN_QWORDS 6
#define SIZE_OF_SHA384_HASH_IN_BYTES (SIZE_OF_SHA384_HASH_IN_QWORDS << 3)
typedef union measurement_u
{
    uint64_t qwords[SIZE_OF_SHA384_HASH_IN_QWORDS];
    uint8_t  bytes[SIZE_OF_SHA384_HASH_IN_BYTES];
} measurement_t;

// REPORTTYPE indicates the reported Trusted Execution Environment (TEE) type, sub-type and version.
typedef union PACKED td_report_type_s
{
    struct
    {
        //
        // Trusted Execution Environment (TEE) Type:
        //     0x00:   SGX
        //     0x7F-0x01:  Reserved (TEE implemented by CPU)
        //     0x80:   Reserved (TEE implemented by SEAM module)
        //     0x81:   TDX
        //     0xFF-0x82:  Reserved (TEE implemented by SEAM module)
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
typedef struct PACKED report_mac_struct_s
{
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
typedef struct PACKED tee_tcb_info_s
{
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
typedef struct PACKED td_info_s
{
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

#define SIZE_OF_TD_REPORT_STRUCT_IN_BYTES 1024

//
// @struct td_report_t
//
// @brief TDREPORT_STRUCT is the output of the TDGMRREPORT function.
//
// If is composed of a generic MAC structure, a SEAMINFO structure and
// a TDX-specific TEE info structure.
//
typedef struct PACKED td_report_s
{
    report_mac_struct_t  report_mac_struct; // < REPORTMACSTRUCT for the TDGMRREPORT
    //
    // Additional attestable elements in the TD’s TCB not reflected in the REPORTMACSTRUCT.CPUSVN.
    // Includes the SEAM measurements.
    //
    tee_tcb_info_t       tee_tcb_info;
    td_info_t            td_info;                       // < TD’s attestable properties
} td_report_t;

#define TDX_ATTR_DEBUG_MASK             (1UL << 0)
#define TDX_ATTR_SEPT_VE_DISABLE_MASK   (1UL << 28)
#define BUFFER_SIZE 2048

void format_measurement_t(char *buffer, size_t buffer_size, const char *name, const measurement_t m) {
    size_t offset = strlen(buffer);
    snprintf(buffer + offset, buffer_size - offset, "%s: ", name);
    for (int i = 0; i < SIZE_OF_SHA384_HASH_IN_BYTES; i++) {
        snprintf(buffer + strlen(buffer), buffer_size - strlen(buffer), "%02x", m.bytes[i]);
    }
    snprintf(buffer + strlen(buffer), buffer_size - strlen(buffer), "\n");
}

void parse_td_info(tdx_report_t* tdx_report, char* buffer, size_t buffer_size) {
    td_report_t* report = (td_report_t*)tdx_report;
    td_info_t* td_info = &report->td_info;

    snprintf(buffer, buffer_size, "attributes: 0x%016lx (%s %s)\n",
             td_info->attributes,
             td_info->attributes & TDX_ATTR_DEBUG_MASK ? "DEBUG" : "NO_DEBUG",
             td_info->attributes & TDX_ATTR_SEPT_VE_DISABLE_MASK ? "SEPT_VE_DISABLE" : "NO_SEPT_VE_DISABLE");

    snprintf(buffer + strlen(buffer), buffer_size - strlen(buffer), "xfam: 0x%016lx\n", td_info->xfam);

    format_measurement_t(buffer, buffer_size, "mr_td", td_info->mr_td);
    format_measurement_t(buffer, buffer_size, "mr_config_id", td_info->mr_config_id);
    format_measurement_t(buffer, buffer_size, "mr_owner", td_info->mr_owner);
    format_measurement_t(buffer, buffer_size, "mr_owner_config", td_info->mr_owner_config);
    format_measurement_t(buffer, buffer_size, "rtmr0", td_info->rtmr0);
    format_measurement_t(buffer, buffer_size, "rtmr1", td_info->rtmr1);
    format_measurement_t(buffer, buffer_size, "rtmr2", td_info->rtmr2);
    format_measurement_t(buffer, buffer_size, "rtmr3", td_info->rtmr3);
}

