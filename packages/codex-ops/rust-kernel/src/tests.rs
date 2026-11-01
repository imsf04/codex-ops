use super::*;
use std::{
    fs,
    path::PathBuf,
    sync::atomic::{AtomicUsize, Ordering},
};

static SERIAL: AtomicUsize = AtomicUsize::new(0);

#[test]
fn oversized_first_stage_and_pending_later_stage_are_explicit() {
    let fixture = Fixture::new();
    let text = format!("CAP {}\n", "x".repeat(2000)).repeat(64);
    fs::write(fixture.root.join("large.log"), &text).unwrap();
    let mut large = options("large.log", "CAP");
    large["before"] = json!(20);
    large["after"] = json!(20);
    large["maxMatches"] = json!(32);
    let first = execute(fixture.request(json!([large.clone()]))).unwrap_err();
    assert_eq!(first.code, "OUTPUT_LIMIT");
    let mixed = execute(fixture.request(json!([options("source.py", "CAP"), large]))).unwrap();
    assert_eq!(mixed["status"], "partial");
    assert_eq!(mixed["kernel"]["omittedStages"], 1);
    assert_eq!(mixed["kernel"]["pendingStages"][0]["path"], "large.log");
    assert_eq!(
        fs::read_to_string(fixture.root.join("large.log")).unwrap(),
        text
    );
}

#[test]
fn credential_filename_fence_prevents_content_observation() {
    let fixture = Fixture::new();
    fs::write(fixture.root.join(".env"), "CAP=PRIVATE_SENTINEL").unwrap();
    let result = execute(fixture.request(json!([options(".env", "CAP")]))).unwrap();
    assert_eq!(
        result["stages"][0]["result"]["error"]["code"],
        "CREDENTIAL_DENIED"
    );
    assert!(!result.to_string().contains("PRIVATE_SENTINEL"));
}

struct Fixture {
    root: PathBuf,
}

impl Fixture {
    fn new() -> Self {
        let root = std::env::temp_dir().join(format!(
            "codex-ops-kernel-{}-{}",
            std::process::id(),
            SERIAL.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(&root).unwrap();
        #[cfg(unix)]
        let root = fs::canonicalize(root).unwrap();
        fs::write(
            root.join("source.py"),
            "CAP = 17\n\ndef cap(value):\n    return min(value, CAP)\n",
        )
        .unwrap();
        Self { root }
    }
    fn request(&self, plans: Value) -> Request {
        serde_json::from_value(
            json!({"root":self.root,"scope":"kernel-tests","read_only":true,
             "deny_credential_names":true,"tool":"investigate","args":{"plans":plans}}),
        )
        .unwrap()
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.root).unwrap();
    }
}

fn options(path: &str, pattern: &str) -> Value {
    json!({"role":"source","path":path,"pattern":pattern,"glob":[],"before":2,"after":3,
           "maxMatches":16,"maxFiles":4})
}

#[test]
fn compound_search_preserves_exact_lines_and_revision() {
    let fixture = Fixture::new();
    let result = execute(fixture.request(json!([options(".", "CAP")]))).unwrap();
    assert_eq!(result["kernel"]["workerStarts"], 1);
    assert_eq!(result["kernel"]["internalOperations"], 2);
    assert_eq!(result["kernel"]["omittedStages"], 0);
    assert_eq!(result["status"], "completed");
    let read = &result["stages"][0]["result"]["context"]["items"][0];
    assert!(read["revision"].as_str().unwrap().len() > 10);
    let source = fs::read_to_string(fixture.root.join("source.py")).unwrap();
    let lines: Vec<_> = source.lines().collect();
    for row in read["items"].as_array().unwrap() {
        assert_eq!(
            row["text"],
            lines[row["line"].as_u64().unwrap() as usize - 1]
        );
    }
    assert!(
        result["stages"][0]["result"]["matchChecks"]
            .as_array()
            .unwrap()
            .iter()
            .all(|c| c["state"] == "unchanged")
    );
}

#[test]
fn no_match_uses_only_search_and_remains_complete() {
    let fixture = Fixture::new();
    let result = execute(fixture.request(json!([options(".", "ABSENT")]))).unwrap();
    assert_eq!(result["kernel"]["internalOperations"], 1);
    assert_eq!(result["status"], "completed");
    assert_eq!(result["stages"][0]["result"]["context"]["items"], json!([]));
}

#[test]
fn boundary_failure_and_mixed_stages_are_explicit() {
    let fixture = Fixture::new();
    let result =
        execute(fixture.request(json!([options(".", "CAP"), options("..", "CAP")]))).unwrap();
    assert_eq!(result["status"], "partial");
    assert_eq!(result["stages"][0]["result"]["status"], "completed");
    assert_eq!(
        result["stages"][1]["result"]["error"]["code"],
        "INVALID_ARGUMENT"
    );
    assert_eq!(
        result["stages"][1]["result"]["error"]["effectState"],
        "none"
    );
}

#[test]
fn invalid_root_credentials_and_mutation_fences_reject() {
    let fixture = Fixture::new();
    for key in ["read_only", "deny_credential_names"] {
        let mut value = json!({"root":fixture.root,"scope":"x","tool":"investigate","read_only":true,
                         "deny_credential_names":true,"args":{"plans":[options(".","CAP")]}});
        value[key] = json!(false);
        assert_eq!(
            execute(serde_json::from_value(value).unwrap())
                .unwrap_err()
                .code,
            "INVALID_ARGUMENT"
        );
    }
    let mut request = fixture.request(json!([options(".", "CAP")]));
    request.root = "relative".into();
    assert!(execute(request).is_err());
    let mut request = fixture.request(json!([options(".", "CAP")]));
    request.scope = String::new();
    assert!(execute(request).is_err());
    let mut request = fixture.request(json!([options(".", "CAP")]));
    request.tool = "write_file".into();
    assert!(execute(request).is_err());
}

#[test]
fn request_bounds_and_unknown_fields_are_rejected() {
    let fixture = Fixture::new();
    assert!(execute(fixture.request(json!([]))).is_err());
    for (key, value) in [
        ("path", json!("")),
        ("pattern", json!("")),
        ("role", json!("")),
        ("glob", json!([""])),
        ("glob", json!(vec!["x"; 33])),
        ("before", json!(21)),
        ("after", json!(21)),
        ("maxMatches", json!(0)),
        ("maxFiles", json!(9)),
        ("unknown", json!(1)),
    ] {
        let mut plan = options(".", "CAP");
        plan[key] = value;
        assert!(execute(fixture.request(json!([plan]))).is_err(), "{key}");
    }
    assert!(execute(fixture.request(json!(vec![options(".", "CAP"); 13]))).is_err());
}

#[test]
fn source_selection_and_exclusions_keep_declared_bounds() {
    let fixture = Fixture::new();
    fs::create_dir(fixture.root.join("verification")).unwrap();
    fs::write(fixture.root.join("verification/noise.py"), "CAP = 999\n").unwrap();
    fs::write(fixture.root.join("second.py"), "CAP = 18\n").unwrap();
    let mut plan = options(".", "CAP");
    plan["glob"] = json!(["**", "!**/verification/**"]);
    plan["maxFiles"] = json!(1);
    let result = execute(fixture.request(json!([plan]))).unwrap();
    assert_eq!(result["status"], "partial");
    let stage = &result["stages"][0]["result"];
    assert_eq!(stage["context"]["items"].as_array().unwrap().len(), 1);
    assert!(stage["omittedMatches"].as_u64().unwrap() > 0);
    assert!(!stage["matches"].to_string().contains("noise.py"));
}

#[test]
fn ranges_merge_and_checks_detect_unavailable_or_changed_lines() {
    let plan: plan::Plan = serde_json::from_value(options(".", "x")).unwrap();
    let rows = vec![
        json!({"path":"a","line":1,"text":"x"}),
        json!({"path":"a","line":3,"text":"x"}),
        json!({"path":"a","line":30,"text":"x"}),
    ];
    let selected = context::select(&rows, 1);
    assert_eq!(
        context::ranges(&selected, &plan),
        json!([{"path":"a","offset":1,"limit":6},{"path":"a","offset":28,"limit":6}])
            .as_array()
            .unwrap()
            .clone()
    );
    let read = json!({"items":[{"path":"a","items":[{"line":1,"text":"y"},{"line":3,"text":"x"},{"bad":1}]}]});
    let checks = context::checks(&selected, &read);
    assert_eq!(
        checks
            .iter()
            .map(|c| c["state"].as_str().unwrap())
            .collect::<Vec<_>>(),
        vec!["changed", "unchanged", "unavailable"]
    );
    assert!(context::incomplete(&json!({"status":"error"})));
    assert!(context::incomplete(&json!({"failed":1})));
    assert!(context::incomplete(&json!({"truncated":true})));
    assert!(!context::incomplete(&json!({"failed":0,"pending":0})));
}

#[test]
fn malformed_native_rows_and_result_budgets_are_explicit() {
    assert!(context::matches(&json!({})).is_err());
    for row in [
        json!({"path":"a","line":0,"text":"x"}),
        json!({"line":1,"text":"x"}),
    ] {
        assert!(context::matches(&json!({"items":[row]})).is_err());
    }
    assert!(fit(&[], &json!("x".repeat(113000))).is_ok_and(|fits| !fits));
    let plans: Vec<plan::Plan> = serde_json::from_value(json!([
        options(".", "x"),
        options(".", "x"),
        options(&"p".repeat(513), "x")
    ]))
    .unwrap();
    let result = result(vec![json!({"result":{"status":"completed"}})], 2, &plans);
    assert_eq!(result["kernel"]["omittedStages"], 2);
    assert_eq!(result["status"], "partial");
    assert_eq!(result["kernel"]["pendingStages"][0]["path"], ".");
    assert_eq!(result["kernel"]["pendingStages"][1]["pathOmitted"], true);
}
