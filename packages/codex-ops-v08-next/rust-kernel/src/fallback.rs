//! Bounded lexical recovery; no guessed repository symbols or permission fallback.
use crate::plan::Plan;
use dsh_ops_core::contract::{Request, Result};
use serde_json::{Value, json};
use std::collections::BTreeSet;

pub const MAX_OPERATIONS: usize = 24;

fn complete(search: &Value) -> bool {
    search["status"] == "completed" && search["scanComplete"] == true && search["complete"] == true
}

pub fn empty(search: &Value) -> bool {
    complete(search) && search["items"].as_array().is_some_and(Vec::is_empty)
}

pub fn role_expansion(plan: &Plan) -> bool {
    plan.anchor_origin == "inferred" && matches!(plan.role.as_str(), "tests" | "configuration")
}

pub fn maximum_calls(plan: &Plan) -> usize {
    2 + usize::from(plan.secondary_pattern.is_some()) + usize::from(role_expansion(plan))
}

fn details(value: &Result<Value>) -> Value {
    match value {
        Ok(found) => json!({"status":found["status"],"scanComplete":found["scanComplete"],
                           "matches":found["items"].as_array().map(Vec::len)}),
        Err(error) => json!({"status":"error","error":error}),
    }
}

fn attempt(request: &Request, args: &Value, calls: &mut usize, trace: &mut Vec<Value>, basis: &str) -> Result<Value> {
    let value = crate::native(request, "grep", crate::plan::grep(args), calls);
    let mut row = details(&value);
    row["basis"] = json!(basis);
    row["pattern"] = args["pattern"].clone();
    trace.push(row);
    value
}

fn retry(request: &Request, args: &mut Value, calls: &mut usize, trace: &mut Vec<Value>, pattern: &str, basis: &str) -> Result<Value> {
    args["pattern"] = json!(pattern);
    attempt(request, args, calls, trace, basis)
}

pub fn search(request: &Request, plan: &Plan, args: &mut Value, calls: &mut usize, trace: &mut Vec<Value>, seeds: &[String]) -> Result<Value> {
    let first = attempt(request, args, calls, trace, "primary")?;
    if !empty(&first) {
        return Ok(first);
    }
    let second = language(request, plan, args, calls, trace, first)?;
    if !source_expansion(plan, &second, seeds) {
        return Ok(second);
    }
    retry(request, args, calls, trace, &seeds.join("|"), "attested-source")
}

fn source_expansion(plan: &Plan, found: &Value, seeds: &[String]) -> bool {
    empty(found) && role_expansion(plan) && !seeds.is_empty()
}

fn language(request: &Request, plan: &Plan, args: &mut Value, calls: &mut usize, trace: &mut Vec<Value>, found: Value) -> Result<Value> {
    match &plan.secondary_pattern {
        Some(pattern) => retry(request, args, calls, trace, pattern, "inferred-language"),
        None => Ok(found),
    }
}

fn identifier(value: &str) -> bool {
    (3..=64).contains(&value.len()) && value.contains('_') && value.bytes().any(|byte| byte.is_ascii_alphabetic())
}

fn text_identifiers(text: &str) -> impl Iterator<Item = &str> {
    text.split(|c: char| !(c.is_ascii_alphanumeric() || c == '_')).filter(|word| identifier(word))
}

fn read_lines(stage: &Value) -> impl Iterator<Item = &Value> {
    stage["result"]["context"]["items"].as_array().into_iter().flatten()
        .flat_map(|file| file["items"].as_array().into_iter().flatten())
}

pub fn seeds(stage: &Value, known: &[String]) -> Vec<String> {
    if stage["result"]["status"] != "completed" {
        return known.to_vec();
    }
    let mut found: BTreeSet<String> = known.iter().cloned().collect();
    for line in read_lines(stage) {
        found.extend(text_identifiers(line["text"].as_str().unwrap_or("")).map(str::to_owned));
    }
    found.into_iter().take(8).collect()
}
