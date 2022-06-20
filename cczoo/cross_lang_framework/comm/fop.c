/* SPDX-License-Identifier: LGPL-3.0-or-later */
/* Copyright (C) 2020 Intel Labs */

#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#include "cross_comm.h"

int64_t fileread(char* f, uint64_t offset, int8_t* buf, uint64_t len) {
	int ret;
	ssize_t bytes_read = 0;
	int fd = 0;

	if(!f || !buf)
		return STATUS_BAD_PARAM;

	/*TODO: Gramine bug, allowed filesystem, open() will change the buffer of f*/
	fd = open((const char*)f, O_RDONLY);
	if (fd < 0) {
		fprintf(stderr, "[error] cannot open '%s'\n", f);
		goto out;
	}

	off_t of = lseek(fd, offset, SEEK_SET);
	if(of != offset) {
		log_error("lseek error, expect %ld, actual %ld", offset, of);
		goto out;
	}

	while (1) {
		ssize_t bytes = read(fd, buf + bytes_read, len - bytes_read);
		if (bytes > 0) {
			bytes_read += bytes;
		} else if (bytes == 0) {
			/* end of file */
			break;
		} else if (errno == EAGAIN || errno == EINTR) {
			continue;
		} else {
			fprintf(stderr, "[error] cannot read '%s'\n", f);
			goto out;
		}
	}

out:
	if(fd>0) {
		ret = close(fd);
		if (ret < 0) {
			fprintf(stderr, "[error] cannot close '%s'\n", f);
		}
	}
	return bytes_read;
}

int64_t filesize(char* f) {
	struct stat st;
	if(!f) {
		return -1;
	}
	if(stat(f, &st)) {
		/* failed to get file size */
		return -1;
	}
	return st.st_size;
}

int64_t filewrite(char* f, uint64_t offset, int8_t* buf, uint64_t len) {
	int ret;
	ssize_t written = 0;

	if(!f || !buf)
		return STATUS_BAD_PARAM;

	int fd = open((char*)f, O_RDWR | O_CREAT, 0666);
	if (fd < 0) {
		fprintf(stderr, "[error] cannot open '%s'\n", f);
		return 0;
	}

	off_t of = lseek(fd, offset, SEEK_SET);
	if(of != offset) {
		log_error("lseek error, expect %ld, actual %ld", offset, of);
		goto out;
	}

	while( written < len ) {
		ssize_t bytes = write(fd, buf + written, len - written);
		if (bytes > 0) {
			written += bytes;
		} else if (bytes == 0) {
			/* may be disk full, break here */
			break;
		} else if (errno == EAGAIN || errno == EINTR) {
			continue;
		} else {
			fprintf(stderr, "[error] cannot write '%s'\n", f);
			goto out;
		}
	}

out:
	ret = close(fd);
	if (ret < 0) {
		fprintf(stderr, "[error] cannot close '%s'\n", f);
	}
	return written;
}

