package GramineJni;

//import gramine_xx;

public class test {
    public static  void main(String[] args)
    {
        gramine_xx jni_so = new gramine_xx();
        gramine_jni jni_so2 = new gramine_jni();
        
        wait(1000);
        System.out.println(jni_so.add(2,3));

        for(int i=0; i<500; i++){
             wait(1000);
             System.out.println(jni_so2.add(2,i));
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

