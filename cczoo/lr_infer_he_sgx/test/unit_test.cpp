#include <gtest/gtest.h>

// #include "infer_client.hpp"
// #include "infer_server.hpp"

int main(int argc, char** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  int rc = RUN_ALL_TESTS();
  return rc;
}
