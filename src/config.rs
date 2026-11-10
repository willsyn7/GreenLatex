//! Host-independent settings shared by the extension and integration harness.
use zed_extension_api::serde_json::{json, Value};

fn merge(base: &mut Value, overrides: Value) {
    match (base, overrides) {
        (Value::Object(base), Value::Object(overrides)) => {
            for (key, value) in overrides {
                merge(base.entry(key).or_insert(Value::Null), value);
            }
        }
        (base, overrides) => *base = overrides,
    }
}

pub fn workspace_configuration(root: &str, python: &str, overrides: Option<Value>) -> Value {
    let helper = format!(
        "{}/scripts/greenlatex.py",
        root.trim_end_matches(['/', '\\'])
    );
    let mut config = json!({"texlab": {
        "build": {
            "executable": python,
            "args": [helper, "build", "%f"],
            "onSave": true,
            "forwardSearchAfter": false,
            "auxDirectory": ".greenlatex",
            "logDirectory": ".greenlatex",
            "pdfDirectory": ".greenlatex"
        },
        "diagnosticsDelay": 300
    }});
    if let Some(overrides) = overrides {
        merge(&mut config, overrides);
    }
    config
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn save_builds_use_the_helper_and_texlab_artifact_directories() {
        let config = workspace_configuration("/project", "/usr/bin/python3", None);
        let build = &config["texlab"]["build"];
        assert_eq!(build["executable"], "/usr/bin/python3");
        assert_eq!(
            build["args"],
            json!(["/project/scripts/greenlatex.py", "build", "%f"])
        );
        assert_eq!(build["onSave"], true);
        assert_eq!(build["forwardSearchAfter"], false);
        for key in ["auxDirectory", "logDirectory", "pdfDirectory"] {
            assert_eq!(build[key], ".greenlatex");
            assert!(
                config["texlab"].get(key).is_none(),
                "artifact options belong under build"
            );
        }
    }

    #[test]
    fn nested_overrides_preserve_sibling_defaults() {
        let config = workspace_configuration(
            "/project",
            "python3",
            Some(json!({
                "texlab": {"build": {"onSave": false}, "diagnosticsDelay": 750}
            })),
        );
        assert_eq!(config["texlab"]["build"]["onSave"], false);
        assert_eq!(config["texlab"]["build"]["executable"], "python3");
        assert_eq!(config["texlab"]["build"]["logDirectory"], ".greenlatex");
        assert_eq!(config["texlab"]["diagnosticsDelay"], 750);
    }

    #[test]
    fn command_argument_overrides_replace_arrays_without_appending() {
        let config = workspace_configuration(
            "/project",
            "python3",
            Some(json!({
                "texlab": {"build": {"executable": "latexmk", "args": ["-xelatex", "%f"]}}
            })),
        );
        assert_eq!(config["texlab"]["build"]["executable"], "latexmk");
        assert_eq!(config["texlab"]["build"]["args"], json!(["-xelatex", "%f"]));
    }

    #[test]
    fn null_and_new_options_are_preserved() {
        let config = workspace_configuration(
            "/project",
            "python3",
            Some(json!({
                "texlab": {"build": {"filename": null}, "chktex": {"onEdit": true}}
            })),
        );
        assert!(config["texlab"]["build"]["filename"].is_null());
        assert_eq!(config["texlab"]["chktex"]["onEdit"], true);
    }

    #[test]
    fn paths_are_arguments_rather_than_shell_commands() {
        for root in [
            "/project with spaces/",
            "/project's $(literal)/",
            "C:\\Users\\Resume Draft\\",
        ] {
            let config = workspace_configuration(root, "C:/Python Tools/python.exe", None);
            let args = config["texlab"]["build"]["args"].as_array().unwrap();
            assert_eq!(args.len(), 3);
            assert_eq!(
                args[0],
                format!(
                    "{}/scripts/greenlatex.py",
                    root.trim_end_matches(['/', '\\'])
                )
            );
            assert_eq!(args[2], "%f");
        }
    }

    #[test]
    fn settings_do_not_leak_between_worktrees() {
        let _first = workspace_configuration(
            "/one",
            "python",
            Some(json!({"texlab": {"build": {"onSave": false}}})),
        );
        let second = workspace_configuration("/two", "python3", None);
        assert_eq!(second["texlab"]["build"]["onSave"], true);
        assert_eq!(
            second["texlab"]["build"]["args"][0],
            "/two/scripts/greenlatex.py"
        );
    }
}
