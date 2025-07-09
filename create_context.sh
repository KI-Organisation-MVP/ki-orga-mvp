#!/bin/bash

# This script finds all relevant source files (Python, Protobuf, YAML, Dockerfile)
# excluding common virtual environment, git, and cache directories. It then aggregates
# the content of these files into a single Markdown file for easy context analysis,
# preserving the directory structure.

# Define the output file
TIMESTAMP=$(date +%Y%m%d)
OUTPUT_FILE="${TIMESTAMP}_kiorgamvp-repo-context.md"

# Create or overwrite the output file, making it empty
> "$OUTPUT_FILE"

# Initialize a variable to keep track of the current directory
current_dir=""

# Find all relevant files, sort them by path, and loop through them.
# Using -print0 and read -d '' handles filenames with spaces or special characters.
find . -type d \( -name "venv" -o -name "__pycache__" -o -name ".git" -o -name ".idea" \) -prune -o -type f \( -name "*.py" -o -name "*.proto" -o -name "*.yaml" -o -name "*.yml" -o -name "Dockerfile" \) -print0 | sort -z | while IFS= read -r -d '' filepath; do
    # Get the directory of the current file
    file_dir=$(dirname "$filepath")

    # If the directory has changed, print a new directory header
    if [[ "$file_dir" != "$current_dir" ]]; then
        current_dir="$file_dir"
        echo -e "\n## Directory: \`${current_dir#./}\`\n" >> "$OUTPUT_FILE"
    fi

    # Use relative path for the header, removing the leading './'
    relative_path="${filepath#./}"

    # Determine the language for the markdown code block from the file extension or name
    extension="${filepath##*.}"
    basename="${filepath##*/}"
    lang="" # Default to empty
    case "$basename" in
        "Dockerfile") lang="dockerfile" ;;
        *".py") lang="python" ;;
        *".proto") lang="protobuf" ;;
        *".yaml"|*".yml") lang="yaml" ;;
    esac

    # Append the file path as a markdown header and the content in a code block
    if [[ -n "$lang" ]]; then
        echo "### \`$basename\`" >> "$OUTPUT_FILE" # Markdown header for the file
        echo "\`\`\`$lang" >> "$OUTPUT_FILE" # Start of code block with language
        cat "$filepath" >> "$OUTPUT_FILE" # Append the file content
        echo -e  "\n\`\`\`" >> "$OUTPUT_FILE" # End of code block
        echo -e "\n---\n" >> "$OUTPUT_FILE" # Add a newline for separation
    fi
done
