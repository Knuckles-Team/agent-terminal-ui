# Goal execution boundary

The frontend does not own an autonomous goal loop. Submit task text to Arbora
with `tuig --prompt TEXT`; backend capability and policy determine execution.
The former Python `/goal` command is retired and has no native compatibility path.
