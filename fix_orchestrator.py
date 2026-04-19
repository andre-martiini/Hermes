import re

with open('functions/slides_orchestrator.py', 'r') as f:
    content = f.read()

# Substituir PPTXBuilder por create_pptx_with_native_svg
new_content = re.sub(
    r'from ppt_master\.svg_to_pptx\.pptx_builder import PPTXBuilder.*?try:.*?builder = PPTXBuilder\(tmpdir\).*?pptx_path = builder\.build_presentation\("final"\)',
    r'''from ppt_master.svg_to_pptx import create_pptx_with_native_svg

        # Gerar o PPTX
        try:
            pptx_path = os.path.join(tmpdir, "exports", f"{job_id}.pptx")
            create_pptx_with_native_svg(tmpdir, "final", pptx_path)''',
    content,
    flags=re.DOTALL
)

with open('functions/slides_orchestrator.py', 'w') as f:
    f.write(new_content)
