/*
 *
 * Copyright (c) 2022 Intel Corporation
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

package GramineJni;

public class gramine_jni {
	public native int get_key(String ip_port, String ca_cert, byte[] key, int key_len);
	public native int get_file_2_buff(String ip_port, String ca_cert, String fname, long offset, byte[] data, int len, int[] ret_len);
	public native int get_file_size(String ip_port, String ca_cert, String fname, long[] ret_len);
	public native int put_result(String ip_port, String ca_cert, String fname, long offset, byte[] data, int len, int[] ret_len);

	static {
		System.loadLibrary("gramine_jni");
	}

	String m_ip_port;
	String m_ca_cert;

	public gramine_jni(String ip_port, String ca_cert) {
		m_ip_port = ip_port;
		m_ca_cert = ca_cert;
	}

	public int GetKey(byte[] key, int key_len) throws Exception {
		int ret = 0;
		try {
			ret = get_key(m_ip_port, m_ca_cert, key, key_len);
		} catch (Exception e) {
			throw new Exception("Failed to get Key.");
		}
		return ret;
	}

	public int GetFile2Buff(String fname, long offset, byte[] data, int len, int[] ret_len) throws Exception {
		int ret = 0;
		try {
			ret = get_file_2_buff(m_ip_port, m_ca_cert, fname, offset, data, len, ret_len);
		} catch (Exception e) {
			throw new Exception("GetFile2Buff Failed.");
		}
		return ret;
	}

	public int GetFileSize(String fname, long[] ret_len) throws Exception {
		int ret = 0;
		try {
			ret = get_file_size(m_ip_port, m_ca_cert, fname, ret_len);
		} catch (Exception e) {
			throw new Exception("GetFileSize Failed.");
		}
		return ret;
	}

	public int PutResult(String fname, long offset, byte[] data, int len, int[] ret_len) throws Exception {
		int ret = 0;
		try {
			ret = put_result(m_ip_port, m_ca_cert, fname, offset, data, len, ret_len);
		} catch (Exception e) {
			throw new Exception("PutResult Failed.");
		}
		return ret;
	}
}

