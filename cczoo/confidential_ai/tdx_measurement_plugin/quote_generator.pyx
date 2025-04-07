# Copyright (c) 2025 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from libc.stdlib cimport malloc, free
from libc.string cimport memset
from libc.stdio cimport printf

cdef extern from "tdx_attest.h":
    ctypedef struct tdx_report_data_t:
        unsigned char d[64]
    ctypedef struct tdx_report_t:
        pass
    ctypedef struct tdx_uuid_t:
        pass

    int tdx_att_get_report(tdx_report_data_t* report_data, tdx_report_t* tdx_report)
    int tdx_att_get_quote(tdx_report_data_t* report_data, void* reserved, unsigned int reserved_size,
                          tdx_uuid_t* selected_att_key_id, unsigned char** p_quote_buf,
                          unsigned int* quote_size, unsigned int flags)
    void tdx_att_free_quote(unsigned char* p_quote_buf)

cdef extern from "td_report_parse.h":
    void parse_td_info(tdx_report_t* report, char* buffer, size_t buffer_size)

def generate_quote():
    cdef tdx_report_data_t report_data
    cdef tdx_report_t tdx_report
    cdef tdx_uuid_t selected_att_key_id
    cdef unsigned char* p_quote_buf = NULL
    cdef unsigned int quote_size = 0

    memset(report_data.d, 0, sizeof(report_data.d))

    if tdx_att_get_report(&report_data, &tdx_report) != 0:
        raise RuntimeError("Failed to get the report")

    cdef char buffer[1024]
    parse_td_info(&tdx_report, buffer, sizeof(buffer))
    parse_result = {}
    for line in buffer.decode('utf-8').split('\n'):
        if line.strip():
            key, value = line.split(':')
            parse_result[key.strip()] = value.strip()

    if tdx_att_get_quote(&report_data, NULL, 0, &selected_att_key_id, &p_quote_buf, &quote_size, 0) != 0:
        raise RuntimeError("Failed to get the quote")

    quote_data = bytes((p_quote_buf[i] for i in range(quote_size)))

    tdx_att_free_quote(p_quote_buf)

    return quote_data

