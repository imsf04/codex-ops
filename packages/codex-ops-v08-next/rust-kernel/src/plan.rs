use dsh_ops_core::contract::{Failure, Request, Result};
use serde::Deserialize;
use serde_json::{Value, json};
use std::path::Path;

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields, rename_all = "camelCase")]
pub struct Plan {
    pub role: String,
    pub path: String,
    pub pattern: String,
    pub glob: Vec<String>,
    pub before: usize,
    pub after: usize,
    pub max_matches: usize,
    pub max_files: usize,
    #[serde(default = "explicit")]
    pub anchor_origin: String,
    #[serde(default)]
    pub secondary_pattern: Option<String>,
}

fn explicit() -> String {
    "explicit".into()
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Plans {
    plans: Vec<Plan>,
}

fn require(condition: bool, message: &str) -> Result<()> {
    if condition {
        Ok(())
    } else {
        Err(Failure::new("INVALID_ARGUMENT", message))
    }
}

fn bounded_text(value: &str, maximum: usize) -> bool {
    !value.is_empty() && value.len() <= maximum
}

fn validate_text(plan: &Plan) -> Result<()> {
    require(
        bounded_text(&plan.path, 4096),
        "path must contain 1..4096 bytes",
    )?;
    require(
        bounded_text(&plan.pattern, 8192),
        "pattern must contain 1..8192 bytes",
    )?;
    require(
        bounded_text(&plan.role, 32),
        "role must contain 1..32 bytes",
    )
}

fn validate_globs(plan: &Plan) -> Result<()> {
    require(plan.glob.len() <= 32, "glob allows at most 32 patterns")?;
    require(
        plan.glob.iter().all(|g| bounded_text(g, 512)),
        "glob patterns require 1..512 bytes",
    )
}

fn validate_bounds(plan: &Plan) -> Result<()> {
    require(
        plan.before <= 20 && plan.after <= 20,
        "context must be 0..20 lines",
    )?;
    require(
        (1..=32).contains(&plan.max_matches),
        "maxMatches must be 1..32",
    )?;
    require((1..=8).contains(&plan.max_files), "maxFiles must be 1..8")
}

fn validate(plan: &Plan) -> Result<()> {
    validate_text(plan)?;
    validate_globs(plan)?;
    validate_bounds(plan)?;
    validate_fallback(plan)
}

fn validate_fallback(plan: &Plan) -> Result<()> {
    require(matches!(plan.anchor_origin.as_str(), "explicit" | "inferred"), "unknown anchorOrigin")?;
    if let Some(pattern) = &plan.secondary_pattern {
        require(plan.anchor_origin == "inferred", "explicit anchors cannot have secondary patterns")?;
        require(bounded_text(pattern, 8192), "secondaryPattern requires 1..8192 bytes")?;
    }
    Ok(())
}

fn authority(request: &Request) -> Result<()> {
    require(
        request.tool == "investigate",
        "kernel accepts only investigate",
    )?;
    require(request.read_only, "kernel requires a read-only request")?;
    require(
        request.deny_credential_names,
        "kernel requires the credential-name fence",
    )
}

fn scope(request: &Request) -> Result<()> {
    require(
        Path::new(&request.root).is_absolute(),
        "root must be absolute",
    )?;
    require(
        bounded_text(&request.scope, 256),
        "scope requires 1..256 bytes",
    )
}

fn plans(args: &Value) -> Result<Vec<Plan>> {
    let parsed: Plans = serde_json::from_value(args.clone())?;
    require(
        (1..=12).contains(&parsed.plans.len()),
        "investigate requires 1..12 plans",
    )?;
    parsed.plans.iter().try_for_each(validate)?;
    Ok(parsed.plans)
}

pub fn parse(request: &Request) -> Result<Vec<Plan>> {
    authority(request)?;
    scope(request)?;
    plans(&request.args)
}

pub fn args(plan: &Plan, root: &str) -> Value {
    let path = Path::new(root).join(&plan.path);
    json!({"path":path,"pattern":plan.pattern,"glob":plan.glob,"before":plan.before,
           "after":plan.after,"maxMatches":plan.max_matches,"maxFiles":plan.max_files})
}

pub fn grep(args: &Value) -> Value {
    json!({"path":args["path"],"pattern":args["pattern"],"glob":args["glob"],
           "limit":args["maxMatches"],"outputMode":"content","lineNumbers":true,
           "beforeContext":0,"afterContext":0,"exactTotal":false})
}

pub fn child(request: &Request, tool: &str, args: Value) -> Request {
    Request {
        root: request.root.clone(),
        scope: request.scope.clone(),
        tool: tool.into(),
        args,
        read_only: true,
        deny_credential_names: true,
        deny_roots: request.deny_roots.clone(),
        output_sink: None,
        output_budget: request.output_budget,
        storage: None,
        write_roots: None,
        root_identity: String::new(),
        job_id: None,
    }
}
