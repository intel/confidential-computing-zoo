//! libtdx_attest FFI Bindings
//!
//! Provides FFI bindings to Intel's libtdx_attest library for TDX quote generation.
//! This is an alternative backend when direct hardware access is available.

use crate::{QuoteError, QuoteGenerator, QuoteMaterial, ReportData};

/// libtdx_attest FFI bindings
mod ffi {
    #[repr(C)]
    pub struct TdxUuid {
        pub d: [u8; 16],
    }

    #[repr(C)]
    pub struct TdxReportData {
        pub d: [u8; 64],
    }

    #[repr(C)]
    pub struct TdxReport {
        pub d: [u8; 1024],
    }
}

/// libtdx_attest-based TDX Quote Generator
///
/// Uses Intel's libtdx_attest library for TDX quote generation.
/// This backend provides direct access to TDX hardware for quote generation.
#[derive(Debug, Clone)]
pub struct LibtdxAttestQuoteGenerator {
    library_path: String,
}

impl LibtdxAttestQuoteGenerator {
    /// Create a new libtdx_attest quote generator with default library path
    pub fn new() -> Self {
        Self::with_library_path(
            std::env::var("TRUCON_TDX_ATTEST_LIB")
                .unwrap_or_else(|_| "libtdx_attest.so".to_string()),
        )
    }

    /// Create a new libtdx_attest quote generator with custom library path
    pub fn with_library_path(library_path: impl Into<String>) -> Self {
        Self {
            library_path: library_path.into(),
        }
    }

    fn resolve_quote_format(&self) -> String {
        "tdx-libtdx-attest".to_string()
    }
}

impl Default for LibtdxAttestQuoteGenerator {
    fn default() -> Self {
        Self::new()
    }
}

impl QuoteGenerator for LibtdxAttestQuoteGenerator {
    fn generate_quote(&self, report_data: &ReportData) -> Result<QuoteMaterial, QuoteError> {
        // Load the library dynamically
        let lib = unsafe {
            libloading::Library::new(&self.library_path).map_err(|e| {
                QuoteError::IoError(std::io::Error::other(format!(
                    "Failed to load libtdx_attest: {}",
                    e
                )))
            })?
        };

        // Get function pointers
        let get_report: libloading::Symbol<
            unsafe extern "C" fn(*const ffi::TdxReportData, *mut ffi::TdxReport) -> u32,
        > = unsafe { lib
            .get(b"tdx_att_get_report")
            .map_err(|e| {
                QuoteError::IoError(std::io::Error::other(format!(
                    "Failed to get tdx_att_get_report: {}",
                    e
                )))
            })? };

        let get_quote: libloading::Symbol<
            unsafe extern "C" fn(
                *const ffi::TdxReportData,
                *const ffi::TdxUuid,
                u32,
                *const ffi::TdxUuid,
                *mut *mut u8,
                *mut u32,
                u32,
            ) -> u32,
        > = unsafe { lib.get(b"tdx_att_get_quote").map_err(|e| {
            QuoteError::IoError(std::io::Error::other(format!(
                "Failed to get tdx_att_get_quote: {}",
                e
            )))
        })? };

        let free_quote: libloading::Symbol<unsafe extern "C" fn(*mut u8) -> u32> =
            unsafe { lib.get(b"tdx_att_free_quote").map_err(|e| {
                QuoteError::IoError(std::io::Error::other(format!(
                    "Failed to get tdx_att_free_quote: {}",
                    e
                )))
            })? };

        // Prepare report data structure
        let mut tdx_report_data = ffi::TdxReportData { d: [0u8; 64] };
        for (i, &byte) in report_data.as_bytes().iter().enumerate() {
            tdx_report_data.d[i] = byte;
        }

        // Get TDX report
        let mut tdx_report = ffi::TdxReport { d: [0u8; 1024] };
        let report_error = unsafe { get_report(&tdx_report_data, &mut tdx_report) };
        if report_error != 0 {
            return Err(QuoteError::GetReportFailed(report_error));
        }

        // Get TDX quote
        let selected_key = std::ptr::null::<ffi::TdxUuid>();
        let pub_key = std::ptr::null::<ffi::TdxUuid>();
        let mut quote_ptr: *mut u8 = std::ptr::null_mut();
        let mut quote_size: u32 = 0;

        let quote_error = unsafe {
            get_quote(
                &tdx_report_data,
                selected_key,
                0,
                pub_key,
                &mut quote_ptr,
                &mut quote_size,
                0,
            )
        };

        if quote_error != 0 || quote_ptr.is_null() {
            return Err(QuoteError::GetQuoteFailed(quote_error));
        }

        // Read quote bytes
        let quote_bytes = unsafe { std::slice::from_raw_parts(quote_ptr, quote_size as usize).to_vec() };

        // Free quote memory
        unsafe { free_quote(quote_ptr) };

        Ok(QuoteMaterial {
            quote: base64::Engine::encode(&base64::engine::general_purpose::STANDARD, &quote_bytes),
            report_data: hex::encode(report_data.as_bytes()),
            quote_format: self.resolve_quote_format(),
        })
    }
}