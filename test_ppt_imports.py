import sys
import os

# Simulando ambiente do Cloud Functions (onde PYTHONPATH recebe o caminho)
sys.path.insert(0, os.path.join(os.getcwd(), 'functions'))
sys.path.insert(0, os.path.join(os.getcwd(), 'functions', 'ppt_master'))

try:
    from finalize_svg import crop_images_in_svg, embed_icons_in_file, embed_images_in_svg, fix_image_aspect_in_svg
    from ppt_master.svg_to_pptx import create_pptx_with_native_svg
    print("Imports OK!")
except ImportError as e:
    print(f"Import Error: {e}")
