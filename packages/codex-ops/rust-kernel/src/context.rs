use crate::plan::Plan;
use dsh_ops_core::contract::{Failure, Result};
use serde_json::{Value, json};
use std::collections::BTreeMap;

pub fn matches(search: &Value) -> Result<&Vec<Value>> {
    let rows = search["items"].as_array().ok_or_else(|| {
        Failure::new(
            "SEARCH_SHAPE",
            "Native search did not return an items array",
        )
    })?;
    rows.iter().try_for_each(validate)?;
    Ok(rows)
}

fn validate(row: &Value) -> Result<()> {
    let valid = row["path"].is_string()
        && row["text"].is_string()
        && row["line"].as_u64().is_some_and(|line| line > 0);
    if valid {
        Ok(())
    } else {
        Err(Failure::new(
            "SEARCH_SHAPE",
            "Native match requires path, line and text",
        ))
    }
}

pub fn select(rows: &[Value], maximum: usize) -> Vec<&Value> {
    let mut paths = Vec::new();
    rows.iter()
        .filter(|row| {
            let path = row["path"].as_str().unwrap();
            if !paths.contains(&path) {
                paths.push(path);
            }
            paths.iter().take(maximum).any(|p| *p == path)
        })
        .collect()
}

fn merge(ranges: &mut Vec<(u64, u64)>, start: u64, end: u64) {
    if let Some(last) = ranges.last_mut() {
        if start <= last.1.saturating_add(1) {
            last.1 = last.1.max(end);
            return;
        }
    }
    ranges.push((start, end));
}

fn file_ranges(path: &str, lines: &mut [u64], plan: &Plan) -> Vec<Value> {
    lines.sort_unstable();
    let mut ranges = Vec::new();
    for line in lines {
        merge(
            &mut ranges,
            line.saturating_sub(plan.before as u64).max(1),
            line.saturating_add(plan.after as u64),
        );
    }
    ranges
        .into_iter()
        .map(|(start, end)| json!({"path":path,"offset":start,"limit":end-start+1}))
        .collect()
}

pub fn ranges(selected: &[&Value], plan: &Plan) -> Vec<Value> {
    let mut grouped: BTreeMap<&str, Vec<u64>> = BTreeMap::new();
    for row in selected {
        grouped
            .entry(row["path"].as_str().unwrap())
            .or_default()
            .push(row["line"].as_u64().unwrap());
    }
    grouped
        .into_iter()
        .flat_map(|(path, mut lines)| file_ranges(path, &mut lines, plan))
        .collect()
}

pub fn empty() -> Value {
    json!({"status":"completed","items":[],"pending":0})
}

fn read_lines(read: &Value) -> BTreeMap<(String, u64), String> {
    let mut lines = BTreeMap::new();
    for item in read["items"].as_array().into_iter().flatten() {
        for row in item["items"].as_array().into_iter().flatten() {
            insert_line(&mut lines, item, row);
        }
    }
    lines
}

fn insert_line(lines: &mut BTreeMap<(String, u64), String>, item: &Value, row: &Value) {
    let path = row.get("path").unwrap_or(&item["path"]);
    if let (Some(path), Some(line), Some(text)) =
        (path.as_str(), row["line"].as_u64(), row["text"].as_str())
    {
        lines.insert((path.into(), line), text.into());
    }
}

fn state(row: &Value, lines: &BTreeMap<(String, u64), String>) -> &'static str {
    match lines.get(&(
        row["path"].as_str().unwrap().into(),
        row["line"].as_u64().unwrap(),
    )) {
        None => "unavailable",
        Some(text) if text == row["text"].as_str().unwrap() => "unchanged",
        Some(_) => "changed",
    }
}

pub fn checks(selected: &[&Value], read: &Value) -> Vec<Value> {
    let lines = read_lines(read);
    selected
        .iter()
        .enumerate()
        .map(|(index, row)| {
            json!({"matchIndex":index,"path":row["path"],
        "line":row["line"],"state":state(row,&lines)})
        })
        .collect()
}

pub fn incomplete(read: &Value) -> bool {
    if matches!(
        read["status"].as_str(),
        Some("error" | "rejected" | "partial")
    ) {
        return true;
    }
    ["failed", "pending", "truncated"]
        .iter()
        .any(|key| positive(&read[*key]))
}

fn positive(value: &Value) -> bool {
    value == true || value.as_u64().is_some_and(|n| n > 0)
}
