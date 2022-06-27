#ifndef UTILS_HPP_
#define UTILS_HPP_

#include <sys/stat.h>
#include <vector>
#include <string>
#include <iostream>

enum class CSVState { UnquotedField, QuotedField, QuotedQuote };

bool file_exists(const std::string& fn);

std::vector<std::string> readCSVRow(const std::string& row);

std::vector<std::vector<std::string>> readCSV(std::istream& in);

std::vector<std::vector<double>> transpose(
    const std::vector<std::vector<double>>& data);

#endif  // UTILS_HPP_

