//! Build script for k1_bus_core.
//!
//! Runs `flatc --rust` on the FlatBuffers schema to generate Rust bindings.
//! The generated code is placed in OUT_DIR and included via `include!()`.

use std::env;
use std::path::{Path, PathBuf};
use std::process::Command;

fn main() {
    let manifest_dir = env::var("CARGO_MANIFEST_DIR").unwrap();
    // Crate lives at k1/k1_bus_core/, schema at k1/bus/envelope/schema.fbs
    // parent() -> k1/, then bus/envelope/schema.fbs
    let schema_path = Path::new(&manifest_dir)
        .parent()
        .unwrap()
        .join("bus")
        .join("envelope")
        .join("schema.fbs");

    let out_dir = PathBuf::from(env::var("OUT_DIR").unwrap());

    // Only re-run if schema changes
    println!("cargo:rerun-if-changed={}", schema_path.display());

    if !schema_path.exists() {
        panic!(
            "FlatBuffers schema not found at {}. \
             Run from the repository root.",
            schema_path.display()
        );
    }

    // Try to find flatc
    let flatc = find_flatc();

    let status = Command::new(&flatc)
        .args([
            "--rust",
            "--gen-all",
            "-o",
            out_dir.to_str().unwrap(),
            schema_path.to_str().unwrap(),
        ])
        .status()
        .unwrap_or_else(|e| panic!("Failed to run flatc at '{}': {}", flatc, e));

    if !status.success() {
        panic!("flatc failed with exit code: {:?}", status.code());
    }

    // flatc generates files under namespace dirs: k1/bus/envelope/envelope_generated.rs
    // We need to flatten it for the include!() macro.
    let generated_dir = out_dir.join("envelope_generated.rs");
    let namespace_file = find_generated_file(&out_dir);

    if let Some(ns_file) = namespace_file {
        if ns_file != generated_dir {
            std::fs::copy(&ns_file, &generated_dir).unwrap_or_else(|e| {
                panic!(
                    "Failed to copy {} -> {}: {}",
                    ns_file.display(),
                    generated_dir.display(),
                    e
                )
            });
        }
    }

    println!("cargo:rustc-cfg=has_flatbuffers");
}

/// Find the flatc binary.  Checks PATH first, then common install locations.
fn find_flatc() -> String {
    // Prefer the winget-installed v25 over the chocolatey v1.12
    let winget_flatc = dirs_next().into_iter().find(|p| {
        std::path::Path::new(p).exists()
    });
    if let Some(path) = winget_flatc {
        return path;
    }

    // Check if flatc is in PATH
    if Command::new("flatc")
        .arg("--version")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
    {
        return "flatc".to_string();
    }

    panic!(
        "flatc not found. Install the FlatBuffers compiler:\n\
         - Windows: winget install Google.FlatBuffers\n\
         - macOS:   brew install flatbuffers\n\
         - Linux:   apt install flatbuffers-compiler"
    );
}

/// Known install locations for flatc (newest first).
fn dirs_next() -> Vec<String> {
    let mut paths = Vec::new();

    // Winget install location
    if let Ok(local) = env::var("LOCALAPPDATA") {
        let winget_dir = Path::new(&local)
            .join("Microsoft")
            .join("WinGet")
            .join("Packages");
        if winget_dir.exists() {
            if let Ok(entries) = std::fs::read_dir(&winget_dir) {
                for entry in entries.flatten() {
                    let name = entry.file_name().to_string_lossy().to_string();
                    if name.starts_with("Google.flatbuffers") {
                        let flatc = entry.path().join("flatc.exe");
                        if flatc.exists() {
                            paths.push(flatc.to_string_lossy().to_string());
                        }
                    }
                }
            }
        }
    }

    // Common Windows locations
    for p in &[
        r"C:\Program Files\FlatBuffers\flatc.exe",
        r"C:\Tools\flatc.exe",
    ] {
        paths.push(p.to_string());
    }

    paths
}

/// Find the generated .rs file, which may be nested under namespace directories.
fn find_generated_file(out_dir: &Path) -> Option<PathBuf> {
    // flatc --rust with namespaced schema may produce:
    //   out_dir/schema_generated.rs          (flat)
    //   out_dir/k1/bus/envelope/schema_generated.rs  (namespaced)
    // We search recursively for any *_generated.rs file.
    fn search(dir: &Path) -> Option<PathBuf> {
        if let Ok(entries) = std::fs::read_dir(dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.is_file() {
                    if let Some(name) = path.file_name().and_then(|n| n.to_str()) {
                        if name.ends_with("_generated.rs") {
                            return Some(path);
                        }
                    }
                } else if path.is_dir() {
                    if let Some(found) = search(&path) {
                        return Some(found);
                    }
                }
            }
        }
        None
    }

    search(out_dir)
}
