
#pragma once

#include <fstream>
#include <iostream>
#include <unordered_map>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include "HttpClient_I.h"
#include "Utils.h"
#include <nlohmann/json.hpp>

using json = nlohmann::json;

namespace AttestClient {
  typedef struct Config {
    std::string attestation_url;
    std::string attestation_type;
    std::string evidence;
    std::string claims;
    std::string api_key;
  } Config;

  inline std::string VerifyEvidence(const AttestClient::Config &config, HttpClient_I &http_client) {
    std::string url = config.attestation_url;
    std::string encoded_quote = config.evidence;
    std::string encoded_claims = config.claims;
    std::string attestation_type = config.attestation_type;

    // headers needed for requests
    std::vector<std::string> headers = {
        "Accept:application/json",
        "Content-Type:application/json"};

    // checks where we are sending the request
    std::stringstream stream;
    if (Utils::case_insensitive_compare(attestation_type, "maa")) {
      stream << "{\"quote\":\"" << encoded_quote
             << "\",\"runtimeData\":{\"data\":\""
             << encoded_claims << "\",\"dataType\":\"JSON\"}}";
    }
    else if (Utils::case_insensitive_compare(attestation_type, "amber")) {
      std::string api_key_header = "x-api-key:" + config.api_key;
      headers.push_back(api_key_header.c_str());
      stream << "{\"quote\":\"" << Utils::base64url_to_base64(encoded_quote) << "\"";

      // if (!encoded_claims.empty()) {
      //   stream << ",\"user_data\":\"" << Utils::base64url_to_base64(encoded_claims) << "\"";
      // }
      stream << "}";
    }
    else {
      throw std::runtime_error("Attestation type was not provided");
    }

    std::string response;
    std::string request_body = stream.str();

    std::cout << "Starting attestation request..." << std::endl;
    std::cout << "Attestation endpoint: " << url << std::endl;

    int status = http_client.InvokeHttpRequest(
        response,
        url,
        HttpClient_I::HttpVerb::POST,
        headers,
        request_body);

    if (status != 0) {
      std::stringstream stream;
      stream << "Failed to reach attestation endpoint. Error Code: " << std::to_string(status);
      throw std::runtime_error(stream.str());
    }

    if (response.empty()) {
      throw std::runtime_error("Empty reponse received from attestation endpoint");
    }

    try {
      json json_response = json::parse(response);
      return json_response["token"];
    }
    catch (const std::exception &e) {
      throw;
    }
  }
};