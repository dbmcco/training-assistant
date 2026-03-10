#!/usr/bin/env bash
set -euo pipefail

EXTRA_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --model)
      EXTRA_ARGS+=("--model" "$2")
      shift 2
      ;;
    --model=*)
      EXTRA_ARGS+=("--model" "${1#--model=}")
      shift
      ;;
    --provider)
      EXTRA_ARGS+=("--provider" "$2")
      shift 2
      ;;
    --provider=*)
      EXTRA_ARGS+=("--provider" "${1#--provider=}")
      shift
      ;;
    --bundle)
      EXTRA_ARGS+=("--bundle" "$2")
      shift 2
      ;;
    --bundle=*)
      EXTRA_ARGS+=("--bundle" "${1#--bundle=}")
      shift
      ;;
    *)
      EXTRA_ARGS+=("$1")
      shift
      ;;
  esac
done

PROMPT=$(cat)
if [[ -z "$PROMPT" ]]; then
  echo "error: empty prompt passed to amplifier executor" >&2
  exit 1
fi

BUNDLE="${AMPLIFIER_BUNDLE:-speedrift}"
exec amplifier run --mode single --output-format json --bundle "$BUNDLE" "${EXTRA_ARGS[@]+${EXTRA_ARGS[@]}}" "$PROMPT"
