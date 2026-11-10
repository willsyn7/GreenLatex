pub mod config;

use std::fs;
use zed_extension_api::{self as zed, serde_json, settings::LspSettings};

#[derive(Default)]
struct GreenLatex {
    texlab: Option<String>,
}

impl zed::Extension for GreenLatex {
    fn new() -> Self {
        Self::default()
    }

    fn language_server_command(
        &mut self,
        id: &zed::LanguageServerId,
        worktree: &zed::Worktree,
    ) -> zed::Result<zed::Command> {
        let settings = LspSettings::for_worktree("texlab", worktree)?;
        let args = settings
            .binary
            .as_ref()
            .and_then(|b| b.arguments.clone())
            .unwrap_or_default();
        let configured = settings.binary.and_then(|b| b.path);
        let command = if let Some(path) = configured.or_else(|| worktree.which("texlab")) {
            path
        } else if let Some(path) = self.texlab.clone() {
            path
        } else {
            zed::set_language_server_installation_status(
                id,
                &zed::LanguageServerInstallationStatus::CheckingForUpdate,
            );
            let (os, arch) = zed::current_platform();
            let arch = match arch {
                zed::Architecture::Aarch64 => "aarch64",
                zed::Architecture::X8664 => "x86_64",
                _ => return Err("Install texlab on PATH for this architecture.".into()),
            };
            let (platform, suffix, kind) = match os {
                zed::Os::Linux => ("linux", "tar.gz", zed::DownloadedFileType::GzipTar),
                zed::Os::Mac => ("macos", "tar.gz", zed::DownloadedFileType::GzipTar),
                zed::Os::Windows => ("windows", "zip", zed::DownloadedFileType::Zip),
            };
            let release = zed::latest_github_release(
                "latex-lsp/texlab",
                zed::GithubReleaseOptions {
                    require_assets: true,
                    pre_release: false,
                },
            )?;
            let name = format!("texlab-{arch}-{platform}.{suffix}");
            let asset = release
                .assets
                .iter()
                .find(|a| a.name == name)
                .ok_or_else(|| {
                    format!("No TexLab release asset {name}; install texlab on PATH.")
                })?;
            let dir = format!("texlab-{}-{arch}-{platform}", release.version);
            let path = format!(
                "{dir}/texlab{}",
                if os == zed::Os::Windows { ".exe" } else { "" }
            );
            if !fs::metadata(&path).is_ok_and(|m| m.is_file()) {
                zed::set_language_server_installation_status(
                    id,
                    &zed::LanguageServerInstallationStatus::Downloading,
                );
                zed::download_file(&asset.download_url, &dir, kind)?;
                zed::make_file_executable(&path)?;
            }
            self.texlab = Some(path.clone());
            path
        };
        Ok(zed::Command {
            command,
            args,
            env: worktree.shell_env(),
        })
    }

    fn language_server_workspace_configuration(
        &mut self,
        _id: &zed::LanguageServerId,
        worktree: &zed::Worktree,
    ) -> zed::Result<Option<serde_json::Value>> {
        let python = worktree
            .which("python3")
            .or_else(|| worktree.which("python"))
            .ok_or("Green LaTeX requires Python 3.10+ on the language server host PATH.")?;
        let overrides = LspSettings::for_worktree("texlab", worktree)?.settings;
        Ok(Some(config::workspace_configuration(
            &worktree.root_path(),
            &python,
            overrides,
        )))
    }
}

zed::register_extension!(GreenLatex);
