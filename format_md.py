import re

def auto_add_markdown_headers(input_filepath, output_filepath):
    with open(input_filepath, 'r', encoding='utf-8') as f:
        text = f.read()

    # 1. Level 3 Headers (e.g., "5.1.1 The BLC vertical...")
    # Matches a digit, dot, digit, dot, digit, space, then text
    text = re.sub(r'^(\d+\.\d+\.\d+\s.*)$', r'### \1', text, flags=re.MULTILINE)

    # 2. Level 2 Headers (e.g., "5.1 Beneficiary Led Construction (BLC)")
    # Matches a digit, dot, digit, space, then text
    text = re.sub(r'^(\d+\.\d+\s[A-Za-z].*)$', r'## \1', text, flags=re.MULTILINE)

    # 3. Level 1 Headers (e.g., "1. Scope of PMAY-U 2.0")
    # Matches a digit, dot, space, then text
    text = re.sub(r'^(\d+\.\s[A-Za-z].*)$', r'# \1', text, flags=re.MULTILINE)

    # 4. Special Top-Level Sections (Definitions, Abbreviations, Annexures)
    text = re.sub(r'^\s*(Definitions for the purpose of the Mission)\s*$', r'# \1', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*(Abbreviations)\s*$', r'# \1', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*(Annexure-\w+)\s*$', r'# \1', text, flags=re.MULTILINE)

    # Save the formatted text
    with open(output_filepath, 'w', encoding='utf-8') as f:
        f.write(text)
    
    print(f"Formatting complete! Saved to {output_filepath}")

# Run it on your file
auto_add_markdown_headers('sauditg.md', 'sauditg_formatted.md')