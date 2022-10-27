/*
 *
 * Copyright (c) 2022 Intel Corporation
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 */

#include "GramineJni_gramine_jni.h"

#define int8_t jbyte
#define int32_t jint
#define int64_t jlong

int get_key(const char* ip_port, const char* ca_cert, int8_t* key, int32_t key_len);
int get_file_size(const char* ip_port, const char* ca_cert, const char* fname, int64_t* ret_len);
/* Java maximum array size is int32 */
int get_file_2_buff(const char* ip_port, const char* ca_cert, const char* fname, int64_t offset, int8_t* data, int32_t len, int32_t* ret_len);
int put_result(const char* ip_port, const char* ca_cert, const char* fname, int64_t offset, int8_t* data, int32_t len, int32_t* ret_len);

/*
 * Class:     GramineJni_gramine_jni
 * Method:    get_key
 * Signature: ([B[B[BI)I
 */
JNIEXPORT jint JNICALL Java_GramineJni_gramine_1jni_get_1key
  (JNIEnv *env, jobject obj, jstring ip_port, jstring ca_cert, jbyteArray key, jint key_len) {
	const char* ip_portPtr = (*env)->GetStringUTFChars(env, ip_port, NULL);
	const char* ca_certPtr = (*env)->GetStringUTFChars(env, ca_cert, NULL);
	jbyte* keyPtr = (*env)->GetByteArrayElements(env, key, NULL);
	int ret = get_key(ip_portPtr, ca_certPtr, keyPtr, key_len);
	(*env)->ReleaseStringUTFChars(env, ip_port, ip_portPtr);
	(*env)->ReleaseStringUTFChars(env, ca_cert, ca_certPtr);
	(*env)->ReleaseByteArrayElements(env, key, keyPtr, 0);
	return ret;
}

/*
 * Class:     GramineJni_gramine_jni
 * Method:    get_file_2_buff
 * Signature: ([B[B[BJ[BI[I)I
 */
JNIEXPORT jint JNICALL Java_GramineJni_gramine_1jni_get_1file_12_1buff
  (JNIEnv *env, jobject obj, jstring ip_port, jstring ca_cert, jstring fname, jlong offset, jbyteArray data, jint len, jintArray ret_len) {
	const char* ip_portPtr = (*env)->GetStringUTFChars(env, ip_port, NULL);
	const char* ca_certPtr = (*env)->GetStringUTFChars(env, ca_cert, NULL);
	const char* fnamePtr = (*env)->GetStringUTFChars(env, fname, NULL);
	jbyte* dataPtr = (*env)->GetByteArrayElements(env, data, NULL);
	jint* ret_lenPtr = (*env)->GetIntArrayElements(env, ret_len, NULL);

	int ret = get_file_2_buff(ip_portPtr, ca_certPtr, (char*)fnamePtr, offset, dataPtr, len, ret_lenPtr);

	(*env)->ReleaseStringUTFChars(env, ip_port, ip_portPtr);
	(*env)->ReleaseStringUTFChars(env, ca_cert, ca_certPtr);
	(*env)->ReleaseStringUTFChars(env, fname, fnamePtr);
	(*env)->ReleaseByteArrayElements(env, data, dataPtr, 0);
	(*env)->ReleaseIntArrayElements(env, ret_len, ret_lenPtr, 0);
	return ret;
}

/*
 * Class:     GramineJni_gramine_jni
 * Method:    get_file_size
 * Signature: ([B[B[B[J)I
 */
JNIEXPORT jint JNICALL Java_GramineJni_gramine_1jni_get_1file_1size
  (JNIEnv *env, jobject obj, jstring ip_port, jstring ca_cert, jstring fname, jlongArray ret_len) {
	const char* ip_portPtr = (*env)->GetStringUTFChars(env, ip_port, NULL);
	const char* ca_certPtr = (*env)->GetStringUTFChars(env, ca_cert, NULL);
	const char* fnamePtr = (*env)->GetStringUTFChars(env, fname, NULL);
	jlong* ret_lenPtr = (*env)->GetLongArrayElements(env, ret_len, NULL);

	int ret = get_file_size(ip_portPtr, ca_certPtr, (char*)fnamePtr, ret_lenPtr);

	(*env)->ReleaseStringUTFChars(env, ip_port, ip_portPtr);
	(*env)->ReleaseStringUTFChars(env, ca_cert, ca_certPtr);
	(*env)->ReleaseStringUTFChars(env, fname, fnamePtr);
	(*env)->ReleaseLongArrayElements(env, ret_len, ret_lenPtr, 0);
	return ret;
}

/*
 * Class:     GramineJni_gramine_jni
 * Method:    put_result
 * Signature: ([B[B[BJ[BI[I)I
 */
JNIEXPORT jint JNICALL Java_GramineJni_gramine_1jni_put_1result
  (JNIEnv *env, jobject obj, jstring ip_port, jstring ca_cert, jstring fname, jlong offset, jbyteArray data, jint len, jintArray ret_len) {
	const char* ip_portPtr = (*env)->GetStringUTFChars(env, ip_port, NULL);
	const char* ca_certPtr = (*env)->GetStringUTFChars(env, ca_cert, NULL);
	const char* fnamePtr = (*env)->GetStringUTFChars(env, fname, NULL);
	jbyte* dataPtr = (*env)->GetByteArrayElements(env, data, NULL);
	jint* ret_lenPtr = (*env)->GetIntArrayElements(env, ret_len, NULL);

	int ret = put_result(ip_portPtr, ca_certPtr, (char*)fnamePtr, offset, dataPtr, len, ret_lenPtr);

	(*env)->ReleaseStringUTFChars(env, ip_port, ip_portPtr);
	(*env)->ReleaseStringUTFChars(env, ca_cert, ca_certPtr);
	(*env)->ReleaseStringUTFChars(env, fname, fnamePtr);
	(*env)->ReleaseByteArrayElements(env, data, dataPtr, 0);
	(*env)->ReleaseIntArrayElements(env, ret_len, ret_lenPtr, 0);
	return ret;
}

