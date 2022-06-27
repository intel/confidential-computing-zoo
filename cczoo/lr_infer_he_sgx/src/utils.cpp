#include "utils.hpp"

bool file_exists(const std::string& fn) {
  struct stat buffer;
  return (stat(fn.c_str(), &buffer) == 0);
}

std::vector<std::string> readCSVRow(const std::string& row) {
  CSVState state = CSVState::UnquotedField;
  std::vector<std::string> fields{""};
  size_t i = 0;  // index of the current field
  for (char c : row) {
    switch (state) {
      case CSVState::UnquotedField:
        switch (c) {
          case ',':  // end of field
            fields.push_back("");
            i++;
            break;
          case '"':
            state = CSVState::QuotedField;
            break;
          default:
            fields[i].push_back(c);
            break;
        }
        break;
      case CSVState::QuotedField:
        switch (c) {
          case '"':
            state = CSVState::QuotedQuote;
            break;
          default:
            fields[i].push_back(c);
            break;
        }
        break;
      case CSVState::QuotedQuote:
        switch (c) {
          case ',':  // , after closing quote
            fields.push_back("");
            i++;
            state = CSVState::UnquotedField;
            break;
          case '"':  // "" -> "
            fields[i].push_back('"');
            state = CSVState::QuotedField;
            break;
          default:  // end of quote
            state = CSVState::UnquotedField;
            break;
        }
        break;
    }
  }
  return fields;
}

std::vector<std::vector<std::string>> readCSV(std::istream& in) {
  std::vector<std::vector<std::string>> table;
  std::string row;
  while (!in.eof()) {
    std::getline(in, row);
    if (in.bad() || in.fail()) {
      break;
    }
    auto fields = readCSVRow(row);
    table.push_back(fields);
  }
  return table;
}

std::vector<std::vector<double>> transpose(
    const std::vector<std::vector<double>>& data) {
  std::vector<std::vector<double>> res(data[0].size(),
                                       std::vector<double>(data.size()));

#pragma omp parallel for collapse(2) \
    num_threads(OMPUtilitiesS::getThreadsAtLevel())
  for (size_t i = 0; i < data[0].size(); i++) {
    for (size_t j = 0; j < data.size(); j++) {
      res[i][j] = data[j][i];
    }
  }
  return res;
}


