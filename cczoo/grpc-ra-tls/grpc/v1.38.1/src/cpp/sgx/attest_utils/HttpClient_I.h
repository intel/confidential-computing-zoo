#pragma once
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

typedef enum HttpClientResult {
  SUCCESS = 0,
  FAILED = 1,
  MISSING_REQUEST_BODY = 2,
} HttpClientResult;

class HttpClient_I {
public:
  enum class HttpVerb {
    GET,
    POST
  };

  /**
   *@brief This function will be used to send a http request
   * @param[in] url, the url endpoint to be called
   * @param[in] http_verb, the HTTP verb (GET or POST)
   * @param[in] headers, a vector of string for each header type needed for the request
   * @param[in] request_body, the request body. This is expected for any POST calls.
   * @param[out] http_response The response received from the endpoint.
   * @return On sucess, the function returns REQUEST_SUCCESS and
   * the http_response is set to the response from the end point.
   * On failure, an error code is returned.
   */
  virtual HttpClientResult InvokeHttpRequest(std::string &http_response,
                                     const std::string &url,
                                     const HttpClient_I::HttpVerb &http_verb,
                                     const std::vector<std::string> &headers,
                                     const std::string &request_body = std::string()) = 0;
};