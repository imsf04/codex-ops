#![forbid(unsafe_code)]
mod context;
mod fallback;
mod plan;

use dsh_ops_core::{
    contract::{Failure, Request, Result},
    dispatch,
};
use serde_json::{Value, json};

fn native(request: &Request, tool: &str, args: Value, calls: &mut usize) -> Result<Value> {
    *calls += 1;
    dispatch(plan::child(request, tool, args))
}

fn partial(search: &Value, omitted: usize, read: &Value, checks: &[Value]) -> bool {
    search["scanComplete"] != true
        || omitted > 0
        || context::incomplete(read)
        || checks.iter().any(|check| check["state"] != "unchanged")
}

fn evidence(search: Value, selected: &[&Value], requested: Vec<Value>, read: Value) -> Value {
    let checks = context::checks(selected, &read);
    let omitted = search["items"].as_array().unwrap().len() - selected.len();
    let status = if partial(&search, omitted, &read, &checks) {
        "partial"
    } else {
        "completed"
    };
    let mut facts = search.clone();
    let matches = facts.as_object_mut().unwrap().remove("items").unwrap();
    json!({"status":status,"effectState":"none","sourceCompleteness":"per-stage",
           "snapshotConsistency":"non-atomic; matched lines compared only","search":facts,
           "matches":matches,"selectedMatches":selected.len(),"omittedMatches":omitted,
           "requestedRanges":requested,"omittedRanges":0,"context":read,"matchChecks":checks})
}

fn search(request: &Request, plan: &plan::Plan, args: &mut Value, calls: &mut usize, trace: &mut Vec<Value>, seeds: &[String]) -> Result<Value> {
    let found = fallback::search(request, plan, args, calls, trace, seeds)?;
    let selected = context::select(context::matches(&found)?, plan.max_files);
    let ranges = context::ranges(&selected, plan);
    let read = if ranges.is_empty() {
        context::empty()
    } else {
        native(request, "read_files", json!({"files":ranges}), calls)?
    };
    Ok(evidence(found.clone(), &selected, ranges, read))
}

fn stage(request: &Request, plan: &plan::Plan, calls: &mut usize, seeds: &[String]) -> Value {
    let mut args = plan::args(plan, &request.root);
    let mut trace = Vec::new();
    let value = match search(request, plan, &mut args, calls, &mut trace, seeds) {
        Ok(value) => value,
        Err(error) => json!({"status":"error","effectState":"none","error":error}),
    };
    if plan.anchor_origin == "explicit" {
        trace.clear();
    }
    json!({"phase":"discovery","role":plan.role,"args":args,"result":value,
           "anchorOrigin":plan.anchor_origin,"searchAttempts":trace})
}

fn fit(stages: &[Value], next: &Value) -> Result<bool> {
    Ok(serde_json::to_vec(stages)?.len() + serde_json::to_vec(next)?.len() < 112000)
}

fn pending(index: usize, plan: &plan::Plan) -> Value {
    let mut value = json!({"planIndex":index,"role":plan.role});
    if plan.path.len() <= 512 {
        value["path"] = json!(plan.path);
    } else {
        value["pathOmitted"] = json!(true);
    }
    value
}

fn result(stages: Vec<Value>, calls: usize, plans: &[plan::Plan]) -> Value {
    let omitted = plans.len() - stages.len();
    let pending: Vec<_> = plans
        .iter()
        .enumerate()
        .skip(stages.len())
        .map(|(index, plan)| pending(index, plan))
        .collect();
    let incomplete = omitted > 0 || stages.iter().any(|s| s["result"]["status"] != "completed");
    json!({"status":if incomplete {"partial"} else {"completed"},"effectState":"none",
           "stages":stages,"kernel":{"version":env!("CARGO_PKG_VERSION"),"workerStarts":1,
           "internalOperations":calls,"operationLimit":fallback::MAX_OPERATIONS,"plannedStages":plans.len(),"omittedStages":omitted,"pendingStages":pending,
           "nextAction":"For pending stages repeat the original query with narrower paths or context; plan indexes refer to the original ordered plans",
           "sourceCompleteness":"bounded, non-atomic read-only stages"}})
}

fn collect(request: &Request, plans: &[plan::Plan], calls: &mut usize) -> Result<Vec<Value>> {
    let mut stages = Vec::new();
    let mut seeds = Vec::new();
    for plan in plans {
        if *calls + fallback::maximum_calls(plan) > fallback::MAX_OPERATIONS {
            break;
        }
        let next = stage(request, plan, calls, &seeds);
        if !fit(&stages, &next)? {
            break;
        }
        seeds = fallback::seeds(&next, &seeds);
        stages.push(next);
    }
    Ok(stages)
}

pub fn execute(request: Request) -> Result<Value> {
    let plans = plan::parse(&request)?;
    let mut calls = 0;
    let stages = collect(&request, &plans, &mut calls)?;
    if stages.is_empty() {
        return Err(Failure::new(
            "OUTPUT_LIMIT",
            "First stage exceeds kernel result budget; narrow context",
        ));
    }
    Ok(result(stages, calls, &plans))
}

#[cfg(test)]
mod tests;
