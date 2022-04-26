package GramineJni;

public class gramine_jni {
	public native int get_key(byte[] key, int key_len);
	public native int get_file_2_buff(byte[] fname, long offset, byte[] data, int len, int[] ret_len);
	public native int get_file_size(byte[] fname, long[] ret_len);
	public native int put_result(byte[] fname, long offset, byte[] data, int len);

	static {
		System.loadLibrary("gramine_jni");
	}
}

