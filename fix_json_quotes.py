import json
import re

with open("data.json", "r", encoding="utf-8") as f:
    content = f.read()

# Replace single-quoted strings that look like JSON arrays
# Pattern: '["item1", "item2"]'  ->  "[\"item1\", \"item2\"]"
def replace_single_quote_arrays(match):
    inner = match.group(1)
    # Escape double quotes inside the inner string
    inner = inner.replace('"', '\\"')
    return f'"{inner}"'

content = re.sub(r"'(\[.*?\])'", replace_single_quote_arrays, content)

# Also handle single quotes around plain strings? Not needed if only arrays are problematic.
# But if any metadata value uses single quotes, uncomment the line below:
# content = re.sub(r"'([^']*)'", r'"\1"', content)

# Write fixed JSON
with open("data_fixed.json", "w", encoding="utf-8") as f:
    f.write(content)

print("Fixed JSON written to data_fixed.json. Replace data.json with this file.")