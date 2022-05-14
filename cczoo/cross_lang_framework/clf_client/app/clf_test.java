import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import GramineJni.*;


public class clf_test {
	public static void main(String[] args) throws InterruptedException {
		jni_test();
	}

	public static void jni_test()
	{
		String ip_port = "VM-0-3-ubuntu:4433";
		String ca_cert = "certs/ca_cert.crt";
		gramine_jni jni_so = new gramine_jni(ip_port.getBytes(), ca_cert.getBytes());

		// demonstrate get key from server
		int key_len = 64;
		byte[] key = new byte[key_len];
		key[0] = 3;
		System.out.println("[before get key],key[0]="+key[0]+" key[1]="+key[1]);
		try {
			jni_so.GetKey(key, key_len);
		} catch (Exception e) {
			System.out.println(e.getMessage());
		}
		System.out.format("[after get key],key[0..]=0x%X-0x%X\n", key[0], key[1]);

		// demonstrate get a server file size
		String fname = "README.md";
		long[] data_len = new long[1];
		try {
			jni_so.GetFileSize(fname.getBytes(), data_len);
		} catch (Exception e) {
			System.out.println(e.getMessage());
		}
		System.out.println("[jni_so.get_file_size]"+fname+" size="+data_len[0]);

		// demonstrate get file content from server
		byte[] data = new byte[(int)data_len[0]];
		int[] ret_len = new int[1];
		try {
			jni_so.GetFile2Buff(fname.getBytes(), 2, data, 10, ret_len);
		} catch (Exception e) {
			System.out.println(e.getMessage());
		}
		System.out.println("[after get data]" + new String(data));

		// demonstrate put result to server
		String output_fname = "2.out";
		try {
			jni_so.PutResult(output_fname.getBytes(), 0, data, 10);
		} catch (Exception e) {
			System.out.println(e.getMessage());
		}
	}

	public static void wait(int ms)
	{
		try
		{
			Thread.sleep(ms);
		}
		catch(InterruptedException ex)
		{
			Thread.currentThread().interrupt();
		}
	}
}
