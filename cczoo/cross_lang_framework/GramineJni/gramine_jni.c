#include "GramineJni_gramine_jni.h"

int secret_prov_test();

/*
 * Class:     GramineJni_gramine_jni
 * Method:    add
 * Signature: (II)I
 */
JNIEXPORT jint JNICALL Java_GramineJni_gramine_1jni_add
  (JNIEnv *env, jobject obj, jint a, jint b) {
    secret_prov_test();
    return a+b;
}

