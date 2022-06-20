import java.io.*;
import java.lang.*;
import java.util.*;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import GramineJni.*;

public class clf_test {
	public static void main(String[] args) throws InterruptedException {
		//jni_local_test();
		jni_remote_test();
	}

	public static void jni_local_test()
	{
		String ip_port = "local";
		String ca_cert = "";
		gramine_jni jni_so = new gramine_jni(ip_port.getBytes(), ca_cert.getBytes());

		// demonstrate get a server file size
		//String fname = "/plain/plain.txt";
		String fname = "/readonly/1.txt";
		System.out.format("\n[test] get file size\n");
		long[] data_len = new long[1];
		try {
			jni_so.GetFileSize(fname.getBytes(), data_len);
		} catch (Exception e) {
			System.out.println(e.getMessage());
		}
		System.out.format("jni_so.GetFileSize(%s) size=%d\n", fname, data_len[0]);

		// demonstrate get file content from local plain filesystem
		byte[] data = new byte[(int)data_len[0]];
		long offset = 0;
		int len = 32;
		for(int i = 0; i<10; i++) {
			System.out.format("\n[test] get data from local plain filesystem. %s, offset=%d, expect len=%d\n", fname, offset, len);
			try {
				int[] ret_len = new int[1];
				jni_so.GetFile2Buff(fname.getBytes(), offset, data, len, ret_len);
				print_array(data, ret_len[0]);
				offset += len;
				if(offset > (int)data_len[0])
					offset = 0;
/*
				int[] ret_len2 = new int[1];
				String output_fname = "/plain/result.out";
				System.out.format("\n[test] write local plain file, %s\n", output_fname);
				jni_so.PutResult(output_fname.getBytes(), offset, data, ret_len[0], ret_len2);
				System.out.format("jni_so.PutResult(%s)\n", output_fname);
*/
			} catch (Exception e) {
				System.out.println(e.getMessage());
				break;
			}
		}

	}

	public static void jni_remote_test()
	{
		String ip_port = "localhost:4433";
		String ca_cert = "certs/ca_cert.crt";
		gramine_jni jni_so = new gramine_jni(ip_port.getBytes(), ca_cert.getBytes());

		// demonstrate get key from server
		int key_len = 64;
		byte[] key = new byte[key_len];
		System.out.format("[test] get key from server\n");
		try {
			jni_so.GetKey(key, key_len);
		} catch (Exception e) {
			System.out.println(e.getMessage());
		}
		System.out.format("key got from server:\n");
		print_array(key, 32);

		// demonstrate get a server file size
		System.out.format("\n[test] get server resource size\n");
		String fname = "README.md";
		long[] data_len = new long[1];
		try {
			jni_so.GetFileSize(fname.getBytes(), data_len);
		} catch (Exception e) {
			System.out.println(e.getMessage());
		}
		System.out.format("jni_so.GetFileSize(%s) size=%d\n", fname, (int)data_len[0]);

		// demonstrate get file content from server
		byte[] data = new byte[(int)data_len[0]];
		int[] ret_len = new int[1];
		int offset = 0;
		int len = 32;
		for(int i = 0; i<2000; i++) {
			System.out.format("\n[test] get data from server. %s, offset=%d, expect len=%d\n", fname, offset, len);
			try {
				jni_so.GetFile2Buff(fname.getBytes(), offset, data, len, ret_len);
				print_array(data, ret_len[0]);
				offset += len;
				if(offset > (int)data_len[0])
					offset = 0;
			} catch (Exception e) {
				System.out.println(e.getMessage());
			}
		}

		// demonstrate put result back to server
		System.out.format("\n[test] put result to server\n");
		String output_fname = "result.out";
		try {
			jni_so.PutResult(output_fname.getBytes(), 0, data, 10, ret_len);
			System.out.format("jni_so.PutResult(%s)", output_fname);
		} catch (Exception e) {
			System.out.println(e.getMessage());
		}
		System.out.format("\n");

	}

	private static void print_array(byte[] d, int len)
	{
		int split = 8;

		System.out.format("len: %d\n", len);
		for(int i = 0; i<len; i++)
		{
			if(i == len-1)
				System.out.format("%02X\n", d[i]);
			else
			{
				if(i!=0 && ((i+1)%split)==0)
					System.out.format("%02X\n", d[i]);
				else
					System.out.format("%02X-", d[i]);
			}
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
