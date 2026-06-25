//! TSM ConfigFS Quote Generator
//!
//! Provides quote generation through Linux TSM (Trusted Security Module) configfs interface.
//! This is the preferred backend when running in a TDX environment with TSM support.

use std::fs;
use std::path::PathBuf;

use crate::{QuoteError, QuoteGenerator, QuoteMaterial, ReportData};

/// TSM-based TDX Quote Generator
///
/// Uses Linux TSM configfs interface for quote generation.
/// This is the preferred backend when running in a TDX environment with TSM support.
#[derive(Debug, Clone)]
pub struct TsmQuoteGenerator {
    report_data_path: PathBuf,
    quote_path: PathBuf,
    report_root_path: PathBuf,
}

impl TsmQuoteGenerator {
    /// Create a new TSM quote generator with default paths
    pub fn new() -> Self {
        Self::with_paths(
            std::env::var("TRUCON_TSM_REPORT_DATA_PATH")
                .map(PathBuf::from)
                .unwrap_or_else(|_| PathBuf::from("/sys/kernel/config/tsm/report/reportdata")),
            std::env::var("TRUCON_TSM_QUOTE_PATH")
                .map(PathBuf::from)
                .unwrap_or_else(|_| PathBuf::from("/sys/kernel/config/tsm/report/outblob")),
            std::env::var("TRUCON_TSM_REPORT_ROOT")
                .map(PathBuf::from)
                .unwrap_or_else(|_| PathBuf::from("/sys/kernel/config/tsm/report")),
        )
    }
    
    /// Create a new TSM quote generator with custom paths
    pub fn with_paths(
        report_data_path: PathBuf,
        quote_path: PathBuf,
        report_root_path: PathBuf,
    ) -> Self {
        Self {
            report_data_path,
            quote_path,
            report_root_path,
        }
    }
    
    fn resolve_quote_format(&self) -> String {
        "tdx-configfs-tsm".to_string()
    }
    
    fn encode_inblob(&self, report_data: &[u8]) -> Vec<u8> {
        let mut inblob = report_data.to_vec();
        inblob.resize(64, 0x00);
        inblob
    }
}

impl Default for TsmQuoteGenerator {
    fn default() -> Self {
        Self::new()
    }
}

impl QuoteGenerator for TsmQuoteGenerator {
    fn generate_quote(&self, report_data: &ReportData) -> Result<QuoteMaterial, QuoteError> {
        let inblob = self.encode_inblob(report_data.as_bytes());
        
        // Write report data to TSM configfs
        fs::write(&self.report_data_path, &inblob)?;
        
        // Verify report data was accepted
        let accepted = fs::read(&self.report_data_path)?;
        if accepted[..report_data.len] != *report_data.as_bytes() {
            return Err(QuoteError::ReportDataMismatch);
        }
        
        // Read generated quote
        let quote_bytes = fs::read(&self.quote_path)?;
        
        Ok(QuoteMaterial {
            quote: base64::Engine::encode(&base64::engine::general_purpose::STANDARD, &quote_bytes),
            report_data: hex::encode(report_data.as_bytes()),
            quote_format: self.resolve_quote_format(),
        })
    }
}

/// Instance-based TSM Quote Generator
///
/// Creates a unique report instance for each quote generation,
/// avoiding potential conflicts with concurrent quote requests.
#[derive(Debug, Clone)]
pub struct TsmInstanceQuoteGenerator {
    report_root_path: PathBuf,
}

impl TsmInstanceQuoteGenerator {
    /// Create a new instance-based TSM quote generator
    pub fn new() -> Self {
        Self::with_path(
            std::env::var("TRUCON_TSM_REPORT_ROOT")
                .map(PathBuf::from)
                .unwrap_or_else(|_| PathBuf::from("/sys/kernel/config/tsm/report")),
        )
    }
    
    /// Create a new instance-based TSM quote generator with custom root path
    pub fn with_path(report_root_path: PathBuf) -> Self {
        Self { report_root_path }
    }
    
    fn resolve_quote_format(&self) -> String {
        "tdx-configfs-tsm".to_string()
    }
    
    fn encode_inblob(&self, report_data: &[u8]) -> Vec<u8> {
        let mut inblob = report_data.to_vec();
        inblob.resize(64, 0x00);
        inblob
    }
    
    fn create_instance_dir(&self) -> Result<PathBuf, QuoteError> {
        let instance_id = uuid::Uuid::new_v4().to_string();
        let report_dir = self.report_root_path.join(format!("report0_{}", instance_id));
        fs::create_dir_all(&report_dir)?;
        Ok(report_dir)
    }
    
    fn cleanup_instance_dir(&self, report_dir: &PathBuf) -> Result<(), QuoteError> {
        if let Ok(entries) = fs::read_dir(report_dir) {
            for entry in entries.flatten() {
                let _ = fs::remove_file(entry.path());
            }
        }
        fs::remove_dir(report_dir)?;
        Ok(())
    }
}

impl Default for TsmInstanceQuoteGenerator {
    fn default() -> Self {
        Self::new()
    }
}

impl QuoteGenerator for TsmInstanceQuoteGenerator {
    fn generate_quote(&self, report_data: &ReportData) -> Result<QuoteMaterial, QuoteError> {
        let report_dir = self.create_instance_dir()?;
        
        let report_data_path = report_dir.join("inblob");
        let quote_path = report_dir.join("outblob");
        
        let inblob = self.encode_inblob(report_data.as_bytes());
        
        // Write report data
        fs::write(&report_data_path, &inblob)?;
        
        // Read generated quote
        let quote_bytes = fs::read(&quote_path)?;
        
        // Cleanup instance directory
        let _ = self.cleanup_instance_dir(&report_dir);
        
        Ok(QuoteMaterial {
            quote: base64::Engine::encode(&base64::engine::general_purpose::STANDARD, &quote_bytes),
            report_data: hex::encode(report_data.as_bytes()),
            quote_format: self.resolve_quote_format(),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_tsm_generator_creation() {
        let generator = TsmQuoteGenerator::new();
        assert_eq!(generator.resolve_quote_format(), "tdx-configfs-tsm");
    }
    
    #[test]
    fn test_tsm_instance_generator_creation() {
        let generator = TsmInstanceQuoteGenerator::new();
        assert_eq!(generator.resolve_quote_format(), "tdx-configfs-tsm");
    }
}