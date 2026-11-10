//! Print the real extension defaults for debugging and protocol integration tests.
use green_latex::config::workspace_configuration;

fn main() {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args.len() != 2 {
        eprintln!("Usage: texlab_config <worktree-root> <python-executable>");
        std::process::exit(2);
    }
    println!("{}", workspace_configuration(&args[0], &args[1], None));
}
