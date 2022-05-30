import java.io.*;
import java.lang.*;
import java.util.*;
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
		System.out.println("[test] get key from server");
		try {
			jni_so.GetKey(key, key_len);
		} catch (Exception e) {
			System.out.println(e.getMessage());
		}
		System.out.format("key got from server:\n");
		print_array(key, 32);

		// demonstrate get a server file size
		System.out.println("\n[test] get server resource size");
		String fname = "README.md";
		long[] data_len = new long[1];
		try {
			jni_so.GetFileSize(fname.getBytes(), data_len);
		} catch (Exception e) {
			System.out.println(e.getMessage());
		}
		System.out.println("jni_so.GetFileSize("+fname+") -> size="+data_len[0]);

		// demonstrate get file content from server
		System.out.println("\n[test] get server resource content");
		byte[] data = new byte[(int)data_len[0]];
		int[] ret_len = new int[1];
		try {
			jni_so.GetFile2Buff(fname.getBytes(), 2, data, 10, ret_len);
			System.out.println("jni_so.GetFile2Buff("+fname+") -> ");
			print_array(data, ret_len[0]);
		} catch (Exception e) {
			System.out.println(e.getMessage());
		}

		// demonstrate put result back to server
		System.out.println("\n[test] put result to server");
		String output_fname = "result.out";
		try {
			jni_so.PutResult(output_fname.getBytes(), 0, data, 10);
			System.out.println("jni_so.PutResult("+output_fname+")");
		} catch (Exception e) {
			System.out.println(e.getMessage());
		}
		System.out.format("\n");
	}

	private static void print_array(byte[] d, int len)
	{
		int split = 8;

		System.out.print("len:"+len+"\n");
		for(int i = 0; i<len; i++)
		{
			if(i == len-1)
				System.out.format("%X\n", d[i]);
			else
			{
				if(i!=0 && ((i+1)%split)==0)
					System.out.format("%X\n", d[i]);
				else
					System.out.format("%X-", d[i]);
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
