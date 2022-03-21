package GramineJni;

public class gramine_jni {
    public native int add(int a,int b);

    static {
        System.loadLibrary("gramine_jni");
    }
}

