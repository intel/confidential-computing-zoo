#include <linux/limits.h>
#define WRAP_KEY_SIZE	16
#define MRSIGNER_LEN	32
#define MRENCLAVE_LEN	32
struct cmd_params {
    const char MRSigner[MRSIGNER_LEN];
    const char MREnclave[MRENCLAVE_LEN];
    uint16_t isv_prod_id;
    uint16_t isv_svn;
    const char secret[WRAP_KEY_SIZE];
    const char port[8];
    const char server_cert_path[PATH_MAX];
    const char server_private_key_path[PATH_MAX];
};

/**
 * Function for parsing command-line parameters of quote_gen
 *
 */
int cmd_params_process(int argc, char **argv, struct cmd_params *params);
