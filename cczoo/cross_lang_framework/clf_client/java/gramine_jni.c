#include "GramineJni_gramine_jni.h"

#define int8_t jbyte
#define int32_t jint
#define int64_t jlong

int get_key(int8_t* ip_port, int8_t* ca_cert, int8_t* key, int32_t key_len);
int get_file_size(int8_t* ip_port, int8_t* ca_cert, char* fname, int64_t* ret_len);
/* Java maximum array size is int32 */
int get_file_2_buff(int8_t* ip_port, int8_t* ca_cert, char* fname, int64_t offset, int8_t* data, int32_t len, int32_t* ret_len);
int put_result(int8_t* ip_port, int8_t* ca_cert, char* fname, int64_t offset, int8_t* data, int32_t len);


/*
 * Class:     GramineJni_gramine_jni
 * Method:    get_key
 * Signature: ([BI)I
 */
JNIEXPORT jint JNICALL Java_GramineJni_gramine_1jni_get_1key
  (JNIEnv *env, jobject obj, jbyteArray ip_port, jbyteArray ca_cert, jbyteArray key, jint key_len) {
	jbyte* ip_portPtr = (*env)->GetByteArrayElements(env, ip_port, NULL);
	jbyte* ca_certPtr = (*env)->GetByteArrayElements(env, ca_cert, NULL);
	jbyte* keyPtr = (*env)->GetByteArrayElements(env, key, NULL);
	int ret = get_key(ip_portPtr, ca_certPtr, keyPtr, key_len);
	(*env)->ReleaseByteArrayElements(env, ip_port, ip_portPtr, 0);
	(*env)->ReleaseByteArrayElements(env, ca_cert, ca_certPtr, 0);
	(*env)->ReleaseByteArrayElements(env, key, keyPtr, 0);
	return ret;
}

/*
 * Class:     GramineJni_gramine_jni
 * Method:    get_file_2_buff
 * Signature: ([BJ[BJ[J)I
 */
JNIEXPORT jint JNICALL Java_GramineJni_gramine_1jni_get_1file_12_1buff
  (JNIEnv *env, jobject obj, jbyteArray ip_port, jbyteArray ca_cert, jbyteArray fname, jlong offset, jbyteArray data, jint len, jintArray ret_len) {
	jbyte* ip_portPtr = (*env)->GetByteArrayElements(env, ip_port, NULL);
	jbyte* ca_certPtr = (*env)->GetByteArrayElements(env, ca_cert, NULL);
	jbyte* fnamePtr = (*env)->GetByteArrayElements(env, fname, NULL);
	jbyte* dataPtr = (*env)->GetByteArrayElements(env, data, NULL);
	jbyte* ret_lenPtr = (*env)->GetByteArrayElements(env, ret_len, NULL);

	int ret = get_file_2_buff(ip_portPtr, ca_certPtr, (char*)fnamePtr, offset, dataPtr, len, (jint*)ret_lenPtr);

	(*env)->ReleaseByteArrayElements(env, ip_port, ip_portPtr, 0);
	(*env)->ReleaseByteArrayElements(env, ca_cert, ca_certPtr, 0);
	(*env)->ReleaseByteArrayElements(env, fname, fnamePtr, 0);
	(*env)->ReleaseByteArrayElements(env, data, dataPtr, 0);
	(*env)->ReleaseByteArrayElements(env, ret_len, ret_lenPtr, 0);
	return ret;
}

/*
 * Class:     GramineJni_gramine_jni
 * Method:    get_file_size
 * Signature: ([B[J)I
 */
JNIEXPORT jint JNICALL Java_GramineJni_gramine_1jni_get_1file_1size
  (JNIEnv *env, jobject obj, jbyteArray ip_port, jbyteArray ca_cert, jbyteArray fname, jlongArray ret_len) {
	jbyte* ip_portPtr = (*env)->GetByteArrayElements(env, ip_port, NULL);
	jbyte* ca_certPtr = (*env)->GetByteArrayElements(env, ca_cert, NULL);
	jbyte* fnamePtr = (*env)->GetByteArrayElements(env, fname, NULL);
	jbyte* ret_lenPtr = (*env)->GetByteArrayElements(env, ret_len, NULL);

	int ret = get_file_size(ip_portPtr, ca_certPtr, (char*)fnamePtr, (jlong*)ret_lenPtr);

	(*env)->ReleaseByteArrayElements(env, ip_port, ip_portPtr, 0);
	(*env)->ReleaseByteArrayElements(env, ca_cert, ca_certPtr, 0);
	(*env)->ReleaseByteArrayElements(env, fname, fnamePtr, 0);
	(*env)->ReleaseByteArrayElements(env, ret_len, ret_lenPtr, 0);
	return ret;
}

/*
 * Class:     GramineJni_gramine_jni
 * Method:    put_result
 * Signature: ([BJ[BI)I
 */
JNIEXPORT jint JNICALL Java_GramineJni_gramine_1jni_put_1result
  (JNIEnv *env, jobject obj, jbyteArray ip_port, jbyteArray ca_cert, jbyteArray fname, jlong offset, jbyteArray data, jint len) {
	jbyte* ip_portPtr = (*env)->GetByteArrayElements(env, ip_port, NULL);
	jbyte* ca_certPtr = (*env)->GetByteArrayElements(env, ca_cert, NULL);
	jbyte* fnamePtr = (*env)->GetByteArrayElements(env, fname, NULL);
	jbyte* dataPtr = (*env)->GetByteArrayElements(env, data, NULL);

	int ret = put_result(ip_portPtr, ca_certPtr, (char*)fnamePtr, offset, dataPtr, len);

	(*env)->ReleaseByteArrayElements(env, ip_port, ip_portPtr, 0);
	(*env)->ReleaseByteArrayElements(env, ca_cert, ca_certPtr, 0);
	(*env)->ReleaseByteArrayElements(env, fname, fnamePtr, 0);
	(*env)->ReleaseByteArrayElements(env, data, dataPtr, 0);
	return ret;
}

