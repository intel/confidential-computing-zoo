#pragma once

#include <boost/archive/iterators/base64_from_binary.hpp>
#include <boost/archive/iterators/binary_from_base64.hpp>
#include <boost/archive/iterators/transform_width.hpp>
#include <boost/algorithm/string.hpp>
#include <cstdlib>
#include <string>
#include <vector>

#define AMBER_API_KEY_NAME "AMBER_API_KEY"

namespace Utils {
    /**
     * Given a base64url encoded string, convert it to binary byte vector
     *
     * param[in] base64_data : string of base64url encoded data
     *
     * returns: vector of unsigned char (byte)
     */
    inline std::vector<unsigned char> base64url_to_binary(const std::string &base64_data) {
        using namespace boost::archive::iterators;
        using It = transform_width<binary_from_base64<std::string::const_iterator>, 8, 6>;
        std::string stringData = base64_data;

        // While decoding base64 url, replace - with + and _ with + and
        // use stanard base64 decode. we dont need to add padding characters. underlying library handles it.
        boost::replace_all(stringData, "-", "+");
        boost::replace_all(stringData, "_", "/");

        return std::vector<unsigned char>(It(std::begin(stringData)), It(std::end(stringData)));
    }

    /**
     * Given a binary byte vector, convert it to base64url encoded string
     *
     * param[in] binary_data:  vector of unsigned char (byte)
     *
     * returns: string of base64url encoded data
     */
    inline std::string binary_to_base64url(const std::vector<unsigned char> &binary_data) {
        using namespace boost::archive::iterators;
        using It = base64_from_binary<transform_width<std::vector<unsigned char>::const_iterator, 6, 8>>;
        auto tmp = std::string(It(std::begin(binary_data)), It(std::end(binary_data)));

        // For encoding to base64url, replace "+" with "-" and "/" with "_"
        boost::replace_all(tmp, "+", "-");
        boost::replace_all(tmp, "/", "_");

        // We do not need to add padding characters while url encoding.
        return tmp;
    }

    inline std::string base64url_to_base64(const std::string &base64_data) {
        std::string stringData = base64_data;

        // While decoding base64 url, replace - with + and _ with + and
        // use stanard base64 decode. we dont need to add padding characters. underlying library handles it.
        boost::replace_all(stringData, "-", "+");
        boost::replace_all(stringData, "_", "/");

        // Needs to calculate the padding needed at the end
        int padding = (4 - base64_data.size() % 4) % 4;
        for (int i = 0; i < padding; i++) {
            stringData.push_back('=');
        }

        return stringData;
    }

    /**
     * Compares two string case insensitive
     *
     * param[in] str1 first string
     * param[in] str2 second string
     *
     * returns: true if equal, false otherwise
     */
    inline bool case_insensitive_compare(const std::string &str1, const std::string &str2) {
        std::string lower_str1 = str1;
        std::string lower_str2 = str2;

        std::transform(lower_str1.begin(), lower_str1.end(), lower_str1.begin(), ::tolower);
        std::transform(lower_str2.begin(), lower_str2.end(), lower_str2.begin(), ::tolower);
        return lower_str2 == lower_str1;
    }
};