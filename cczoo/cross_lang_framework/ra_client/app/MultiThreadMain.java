import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import GramineJni.*;

class SyncedCounter {
    private int counter = 0;

    public int getCounter() {
        return counter;
    }

    public synchronized void increment() {
        counter = counter + 1;
    }

}

public class MultiThreadMain {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executorService = Executors.newFixedThreadPool(8);

        SyncedCounter syncedCounter = new SyncedCounter();

        for(int i = 0; i < 10000; i++) {
            executorService.submit(() -> syncedCounter.increment());
        }

        executorService.shutdown();
        executorService.awaitTermination(30, TimeUnit.SECONDS);

        System.out.println("Final Count is: " + syncedCounter.getCounter());

		gramine_jni jni_so = new gramine_jni();

		int key_len = 64;
		byte[] key = new byte[key_len];
		System.out.println("[before get key],key[0]="+key[0]+" key[1]="+key[1]);
		jni_so.get_key(key, key_len);
		System.out.format("[after get key],key[0..]=0x%X-0x%X\n", key[0], key[1]);

        jni_test();
    }

    public static void jni_test()
    {
        gramine_xx jni_so = new gramine_xx();
        gramine_jni jni_so2 = new gramine_jni();

        wait(1000);
        System.out.println(jni_so.add(2,3));

        for(int i=0; i<1; i++){
             wait(1000);
             //System.out.println(jni_so2.add(2,i));
             System.out.println(".");
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
