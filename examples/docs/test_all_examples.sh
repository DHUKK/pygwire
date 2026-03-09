#!/usr/bin/env bash
# Test all documentation examples to ensure they run without errors

set -e  # Exit on first error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Examples that require actual network connections (skip in tests)
SKIP_EXAMPLES=(
    "index_connection.py"
    "index_subclass.py"
)

echo "Testing all documentation examples..."
echo

for script in "$SCRIPT_DIR"/*.py; do
    basename_script="$(basename "$script")"

    if [[ "$basename_script" == "test_all_examples.py" ]]; then
        continue
    fi

    # Check if this example should be skipped
    skip=false
    for skip_example in "${SKIP_EXAMPLES[@]}"; do
        if [[ "$basename_script" == "$skip_example" ]]; then
            skip=true
            break
        fi
    done

    if [[ "$skip" == true ]]; then
        echo "Skipping: $basename_script (requires network)"
        continue
    fi

    echo "Testing: $basename_script"
    uv run python "$script" > /dev/null 2>&1
    echo "  ✓ Passed"
done

echo
echo "All testable documentation examples passed!"
echo "(Skipped examples that require actual PostgreSQL connections)"
