package GramineJni;

public class gramine_jni {
	public native int get_key(byte[] ip_port, byte[] ca_cert, byte[] key, int key_len);
	public native int get_file_2_buff(byte[] ip_port, byte[] ca_cert, byte[] fname, long offset, byte[] data, int len, int[] ret_len);
	public native int get_file_size(byte[] ip_port, byte[] ca_cert, byte[] fname, long[] ret_len);
	public native int put_result(byte[] ip_port, byte[] ca_cert, byte[] fname, long offset, byte[] data, int len);

	static {
		System.loadLibrary("gramine_jni");
	}

	byte[] m_ip_port;
	byte[] m_ca_cert;

	public gramine_jni(byte[] ip_port, byte[] ca_cert) {
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

	public int GetFile2Buff(byte[] fname, long offset, byte[] data, int len, int[] ret_len) throws Exception {
		int ret = 0;
		try {
			ret = get_file_2_buff(m_ip_port, m_ca_cert, fname, offset, data, len, ret_len);
		} catch (Exception e) {
			throw new Exception("GetFile2Buff Failed.");
		}
		return ret;
	}

	public int GetFileSize(byte[] fname, long[] ret_len) throws Exception {
		int ret = 0;
		try {
			ret = get_file_size(m_ip_port, m_ca_cert, fname, ret_len);
		} catch (Exception e) {
			throw new Exception("GetFileSize Failed.");
		}
		return ret;
	}

	public int PutResult(byte[] fname, long offset, byte[] data, int len) throws Exception {
		int ret = 0;
		try {
			ret = put_result(m_ip_port, m_ca_cert, fname, offset, data, len);
		} catch (Exception e) {
			throw new Exception("PutResult Failed.");
		}
		return ret;
	}
}

