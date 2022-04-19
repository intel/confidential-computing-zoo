package GramineJni;

public class gramine_jni {
	public native int get_key(byte[] key, int key_len);
	public native int get_file_2_buff(byte[] fname, byte[] data, long len, long[] ret_len);
	public native int get_file_2_file(byte[] src_file, byte[] dest_file);

	static {
		System.loadLibrary("gramine_jni");
	}
}

