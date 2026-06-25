//! TDX Quote Generation Library
//!
//! Provides quote generation for Intel TDX attestation through two backends:
//! - TSM/configfs: Uses Linux TSM (Trusted Security Module) configfs interface
//! - libtdx_attest: Uses Intel libtdx_attest library directly
//!
//! # Quote Generation Flow
//!
//! 1. Prepare 64-byte report_data with binding digest
//! 2. Write report_data to TSM configfs or call libtdx_attest
//! 3. Read generated quote from TSM configfs or libtdx_attest
//! 4. Return base64-encoded quote and metadata

pub mod tsm;
pub mod libtdx_attest;

use std::path::PathBuf;

use thiserror::Error;

#[derive(Debug, Error)]
pub enum QuoteError {
    #[error("Report data path not found: {0}")]
    ReportDataPathNotFound(PathBuf),
    
    #[error("Quote path not found: {0}")]
    QuotePathNotFound(PathBuf),
    
    #[error("TSM report root not found: {0}")]
    ReportRootNotFound(PathBuf),
    
    #[error("Report data must not exceed 64 bytes, got {0} bytes")]
    ReportDataTooLarge(usize),
    
    #[error("TSM report data did not retain expected binding prefix")]
    ReportDataMismatch,
    
    #[error("libtdx_attest get_report failed with error code: 0x{0:04x}")]
    GetReportFailed(u32),
    
    #[error("libtdx_attest get_quote failed with error code: 0x{0:04x}")]
    GetQuoteFailed(u32),
    
    #[error("IO error: {0}")]
    IoError(#[from] std::io::Error),
    
    #[error("Base64 decode error: {0}")]
    Base64DecodeError(#[from] base64::DecodeError),
}

/// Quote material returned from TDX quote generation
#[derive(Debug, Clone)]
pub struct QuoteMaterial {
    /// Base64-encoded TDX quote
    pub quote: String,
    /// The report_data that was used for quote generation
    pub report_data: String,
    /// Quote format identifier
    pub quote_format: String,
}

/// Report data for TDX quote generation (64 bytes)
#[derive(Debug, Clone)]
pub struct ReportData {
    data: [u8; 64],
    len: usize,
}

impl ReportData {
    /// Create report data from a binding digest
    pub fn from_digest(digest: &[u8]) -> Result<Self, QuoteError> {
        if digest.len() > 64 {
            return Err(QuoteError::ReportDataTooLarge(digest.len()));
        }
        
        let mut data = [0u8; 64];
        data[..digest.len()].copy_from_slice(digest);
        
        Ok(Self {
            data,
            len: digest.len(),
        })
    }
    
    /// Get the raw bytes of the report data
    pub fn as_bytes(&self) -> &[u8] {
        &self.data[..self.len]
    }
    
    /// Get the full 64-byte aligned bytes (padded with zeros)
    pub fn as_aligned_bytes(&self) -> &[u8; 64] {
        &self.data
    }
}

/// TDX Quote Generator trait
pub trait QuoteGenerator: Send + Sync {
    /// Generate a TDX quote with the given report data
    fn generate_quote(&self, report_data: &ReportData) -> Result<QuoteMaterial, QuoteError>;
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_report_data_from_digest() {
        let digest = b"test_digest_1234567890";
        let report_data = ReportData::from_digest(digest).unwrap();
        
        assert_eq!(report_data.len, 24);
        assert_eq!(report_data.as_bytes(), digest);
    }
    
    #[test]
    fn test_report_data_too_large() {
        let large_digest = vec![0u8; 65];
        let result = ReportData::from_digest(&large_digest);
        
        assert!(result.is_err());
    }
    
    #[test]
    fn test_report_data_aligned_bytes() {
        let digest = b"short";
        let report_data = ReportData::from_digest(digest).unwrap();
        
        let aligned = report_data.as_aligned_bytes();
        assert_eq!(aligned[..5], *b"short");
        assert_eq!(aligned[5], 0x00);
    }
}