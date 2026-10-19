#!/usr/bin/env bash
# UI-TARS-1.5-7B grounder/agent on llama-server, fully on GPU.
M=/home/lenerystia/Models/llama.cpp-cache/UI-TARS-1.5-7B
exec llama-server \
  -m "$M/UI-TARS-1.5-7B.Q8_0.gguf" \
  --mmproj "$M/UI-TARS-1.5-7B.mmproj-f16.gguf" \
  -ngl 99 -c 16384 --host 127.0.0.1 --port 8081 "$@"
