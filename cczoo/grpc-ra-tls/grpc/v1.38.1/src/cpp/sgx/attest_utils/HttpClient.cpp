//-------------------------------------------------------------------------------------------------
// <copyright file="HttpClient.cpp" company="Microsoft Corporation">
// Copyright (c) Microsoft Corporation.  All rights reserved.
// </copyright>
//-------------------------------------------------------------------------------------------------

#include <math.h>
#include <fstream>
#include <iostream>
#include <unordered_map>
#include <stdio.h>
#include <unistd.h>
#include "HttpClient.h"

#define HTTP_STATUS_OK 200
#define HTTP_STATUS_BAD_REQUEST 400
#define HTTP_STATUS_RESOURCE_NOT_FOUND 404
#define HTTP_STATUS_TOO_MANY_REQUESTS 429
#define HTTP_STATUS_INTERNAL_SERVER_ERROR 500
#define MAX_RETRIES 3

using namespace std;

HttpClientResult HttpClient::InvokeHttpRequest(std::string& http_response,
                                                const std::string& url,
                                                const HttpClient_I::HttpVerb& http_verb,
                                                const std::vector<std::string>& header_list,
                                                const std::string& request_body) {

    // Set the the headers for the request
    struct curl_slist* headers = NULL;
    for (const auto &header : header_list) {
        headers = curl_slist_append(headers, header.c_str());
    }
    curl_easy_setopt(curl_handle, CURLOPT_HTTPHEADER, headers);

    // Send a pointer to a std::string to hold the response from the end
    // point along with the handler function.
    std::string response;
    curl_easy_setopt(curl_handle, CURLOPT_WRITEFUNCTION, WriteResponseCallback);
    curl_easy_setopt(curl_handle, CURLOPT_WRITEDATA, &response);

    // Set the url of the end point that we are trying to talk to.
    curl_easy_setopt(curl_handle, CURLOPT_URL, url.c_str());

    // Enable SSL/TLS for the connection
    curl_easy_setopt(curl_handle, CURLOPT_SSL_VERIFYPEER, 1L);
    curl_easy_setopt(curl_handle, CURLOPT_SSL_VERIFYHOST, 2L);

    // Set SSL versions to be used
    curl_easy_setopt(curl_handle, CURLOPT_SSLVERSION, CURL_SSLVERSION_TLSv1_2);

    // SUSE Linux uses different SSL cert path than Ubuntu
    std::string ca_cert_path("/etc/ssl/ca-bundle.pem");
    if (access(ca_cert_path.c_str(), F_OK) != -1)
        curl_easy_setopt(curl_handle, CURLOPT_CAINFO, ca_cert_path.c_str());

    if (http_verb == HttpClient::HttpVerb::POST) {
        if (request_body.empty()) {
            fprintf(stderr, "Request body missing for POST request");
            return HttpClientResult::MISSING_REQUEST_BODY;
        }

        // Set Http verb as POST
        curl_easy_setopt(curl_handle, CURLOPT_CUSTOMREQUEST, "POST");

        // set the payload that will be sent to the endpoint.
        curl_easy_setopt(curl_handle, CURLOPT_POSTFIELDS, request_body.c_str());
        curl_easy_setopt(curl_handle, CURLOPT_POSTFIELDSIZE, request_body.size());
    }

    // Adding timeout for 300 sec
    curl_easy_setopt(curl_handle, CURLOPT_TIMEOUT, 300L);
    CURLcode res;

    uint8_t retries = 0;
    while ((res = curl_easy_perform(curl_handle)) == CURLE_OK) {
        long response_code = HTTP_STATUS_OK;
        curl_easy_getinfo(curl_handle, CURLINFO_RESPONSE_CODE, &response_code);

        if (HTTP_STATUS_OK == response_code) {
            http_response = response;
            if (http_response.size() == 0) {
                fprintf(stderr, "Empty http response received");
            }

            break;
        }
        else if (response_code == HTTP_STATUS_RESOURCE_NOT_FOUND ||
            response_code == HTTP_STATUS_TOO_MANY_REQUESTS ||
            response_code >= HTTP_STATUS_INTERNAL_SERVER_ERROR) {
            if (retries == MAX_RETRIES) {
                fprintf(stderr, "HTTP request failed with response code: %lu, description: %s\n\n", response_code, response.c_str());
                break;
            }
            fprintf(stderr, "HTTP request failed with response code: %lu, description: %s\n\n", response_code, response.c_str());

            // Retry with backoff 30 -> 60 -> 120 seconds
            std::this_thread::sleep_for(
                std::chrono::seconds(
                    static_cast<long long>(30 * pow(2.0, static_cast<double>(retries++)))
                ));

            response = std::string();
            continue;
        }
        else
        {
            fprintf(stderr, "HTTP request failed with response code: %lu, description: %s\n\n", response_code, response.c_str());
            break;
        }
    }

    if (res != CURLE_OK) {
        string error = std::string("Failed sending curl_handle request with error:") + std::string(curl_easy_strerror(res));
        fprintf(stderr, "%s", error.c_str());
        curl_slist_free_all(headers);
        return HttpClientResult::FAILED;
    }

    curl_slist_free_all(headers);

    return HttpClientResult::SUCCESS;
}

size_t HttpClient::WriteResponseCallback(void* contents, size_t size, size_t nmemb, void* response)
{
    if (response == nullptr ||
        contents == nullptr) {
        return 0;
    }
    std::string* responsePtr = reinterpret_cast<std::string*>(response);

    char* contentsStr = (char*)contents;
    size_t contentsSize = size * nmemb;

    responsePtr->insert(responsePtr->end(), contentsStr, contentsStr + contentsSize);

    return contentsSize;
}
