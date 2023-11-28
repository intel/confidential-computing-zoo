//-------------------------------------------------------------------------------------------------
// <copyright file="HttpClient.h" company="Microsoft Corporation">
// Copyright (c) Microsoft Corporation.  All rights reserved.
// </copyright>
//-------------------------------------------------------------------------------------------------

#pragma once

#include <curl/curl.h>
#include <chrono>
#include <thread>
#include <math.h>
#include <fstream>
#include <iostream>
#include <unordered_map>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <vector>
#include "HttpClient_I.h"


class HttpClient : public HttpClient_I{
public:
    HttpClient() {
        curl_global_cleanup();
        curl_handle = curl_easy_init();
        if (curl_handle == nullptr) {
            fprintf(stderr, "Failed to initialize curl_handle for http request.");
            curl_global_cleanup();
            exit(1);
        }
    }

    ~HttpClient() {
        curl_easy_cleanup(curl_handle);
        curl_global_cleanup();
    }

    /**
     *@brief This function will be used to send a http request
     * @param[in] url, the url endpoint to be called
     * @param[in] http_verb, the HTTP verb (GET or POST)
     * @param[in] request_body, the request body. This is expected for any POST calls.
     * @param[out] http_response The response received from the endpoint.
     * @return On sucess, the function returns REQUEST_SUCCESS and
     * the http_response is set to the response from the end point.
     * On failure, an error code is returned.
     */
    HttpClientResult InvokeHttpRequest(std::string &http_response,
                              const std::string &url,
                              const HttpClient::HttpVerb &http_verb,
                              const std::vector<std::string>& headers,
                              const std::string &request_body = std::string()) override;

private:
    CURL *curl_handle;

    /**
     * @brief CURL Callback to write response to a user specified pointer
     */
    static size_t WriteResponseCallback(void* contents, size_t size, size_t nmemb, void* response);

};