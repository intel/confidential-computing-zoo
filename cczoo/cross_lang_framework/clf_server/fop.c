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
#include "clf_server.h"

uint64_t fileread(int8_t* f, uint64_t offset, uint8_t* buf, uint64_t len) {
	int ret;
	ssize_t bytes_read = 0;

	int fd = open((char*)f, O_RDONLY);
	if (fd < 0) {
		fprintf(stderr, "[error] cannot open '%s'\n", f);
		return 0;
	}

	lseek(fd, offset, SEEK_SET);

	while (1) {
		ssize_t ret = read(fd, buf + bytes_read, len - bytes_read);
		if (ret > 0) {
			bytes_read += ret;
		} else if (ret == 0) {
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
	ret = close(fd);
	if (ret < 0) {
		fprintf(stderr, "[error] cannot close '%s'\n", f);
	}
	return bytes_read;
}

int64_t get_file_size(char* f) {
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

uint64_t filewrite(int8_t* f, uint64_t offset, uint8_t* buf, uint64_t len) {
	int ret;
	ssize_t written = 0;

	int fd = open((char*)f, O_RDWR | O_CREAT | O_TRUNC, 0600);
	if (fd < 0) {
		fprintf(stderr, "[error] cannot open '%s'\n", f);
		return 0;
	}

	lseek(fd, offset, SEEK_SET);

	while( written < len ) {
		ssize_t ret = write(fd, buf + written, len - written);
		if (ret > 0) {
			written += ret;
		} else if (ret == 0) {
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

