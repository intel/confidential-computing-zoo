#include "GramineJni_gramine_jni.h"

#define uint8_t jbyte
#define uint32_t jint

int secret_prov_test();
int get_key(uint8_t* key, uint32_t key_len);

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

/*
 * Class:     GramineJni_gramine_jni
 * Method:    get_key
 * Signature: ([BI)I
 */
JNIEXPORT jint JNICALL Java_GramineJni_gramine_1jni_get_1key
  (JNIEnv *env, jobject obj, jbyteArray key, jint key_len) {
	jbyte* bufferPtr = (*env)->GetByteArrayElements(env, key, NULL);
	get_key(bufferPtr, key_len);
	(*env)->ReleaseByteArrayElements(env, key, bufferPtr, 0);
	return 0;
}

/*
 * Class:     GramineJni_gramine_jni
 * Method:    get_file_2_buff
 * Signature: ([B[BJ[J)I
 */
JNIEXPORT jint JNICALL Java_GramineJni_gramine_1jni_get_1file_12_1buff
  (JNIEnv *env, jobject obj, jbyteArray fname, jbyteArray data, jlong len, jlongArray ret_len) {
	return 0;

}

/*
 * Class:     GramineJni_gramine_jni
 * Method:    get_file_2_file
 * Signature: ([B[B)I
 */
JNIEXPORT jint JNICALL Java_GramineJni_gramine_1jni_get_1file_12_1file
  (JNIEnv *env, jobject obj, jbyteArray src_file, jbyteArray dest_file) {
	return 0;
}

