#![forbid(unsafe_code)]
use dsh_ops_core::contract::{
    Failure, Result,
    envelope::{self, Budget},
};
use serde_json::{Value, json};
use std::io::{Read, Write};

fn input() -> Result<Vec<u8>> {
    let mut bytes = Vec::new();
    std::io::stdin()
        .take((envelope::MAX_REQUEST_BYTES + 1) as u64)
        .read_to_end(&mut bytes)?;
    Ok(bytes)
}

fn execute(budget: &mut Budget) -> Result<Value> {
    let mut decoded = envelope::decode(&input()?)?;
    *budget = decoded.budget;
    decoded.request.output_budget = budget.max_bytes;
    let timeout = budget.timeout_ms;
    std::thread::spawn(move || {
        std::thread::sleep(std::time::Duration::from_millis(timeout));
        std::process::exit(124);
    });
    codex_ops_kernel::execute(decoded.request)
}

fn output() -> Result<Vec<u8>> {
    let mut budget = Budget::default();
    let value = match execute(&mut budget) {
        Ok(value) => value,
        Err(error) => json!({"status":"error","effectState":"none","error":error}),
    };
    envelope::encode_result(&value, budget, false)
}

fn main() -> Result<()> {
    if std::env::args().any(|arg| arg == "--version") {
        println!("codex-ops-kernel {}", env!("CARGO_PKG_VERSION"));
        return Ok(());
    }
    let bytes = output().map_err(|err| Failure::new("OUTPUT_ERROR", err.message))?;
    std::io::stdout().lock().write_all(&bytes)?;
    Ok(())
}
