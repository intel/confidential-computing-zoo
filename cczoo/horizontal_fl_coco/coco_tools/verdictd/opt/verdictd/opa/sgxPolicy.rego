
package policy

# By default, deny requests.
default allow = false

allow {
    mrEnclave_is_grant
    mrSigner_is_grant
    input.productId >= data.productId
    input.svn >= data.svn
}

mrEnclave_is_grant {
    count(data.mrEnclave) == 0
}
mrEnclave_is_grant {
    count(data.mrEnclave) > 0
    input.mrEnclave == data.mrEnclave[_]
}

mrSigner_is_grant {
    count(data.mrSigner) == 0
}
mrSigner_is_grant {
    count(data.mrSigner) > 0
    input.mrSigner == data.mrSigner[_]
}
